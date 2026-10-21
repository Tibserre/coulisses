// Coulisses, the app in the Dock (ADR 0034).
//
// It starts the local service (`coulisses-app`, through uv, offline) unless one already
// answers, waits for it, and shows the interface in its own window. Quitting (⌘Q) asks
// first while a recording or a processing runs, then stops the service it started: nothing
// runs once the app is closed. The service's output goes to ~/Library/Logs/Coulisses.
//
// Built by `scripts/construire.py`, the app carries its own Python, interface and tools,
// and runs the service from them (ADR 0040). Built by `scripts/installer-lanceur.sh`, it
// runs the service from a repository: the project's folder, uv and the PATH are written
// into Info.plist, with its variant: « Coulisses (dév) » (`--dev`) has its own name, port,
// data, log and permissions, and may run one of the repository's worktrees instead
// (COULISSES_PROJET, `scripts/tester-branche.sh`).

import AppKit
import UserNotifications
import WebKit

#if COULISSES_SPARKLE
    import Sparkle
#endif

let resourcesDir = Bundle.main.resourceURL ?? Bundle.main.bundleURL
let bundledPython = resourcesDir.appendingPathComponent("python/bin/python3")
let isStandalone = FileManager.default.isExecutableFile(atPath: bundledPython.path)
let settings = Bundle.main.infoDictionary ?? [:]
let installedProject = settings["CoulissesProjet"] as? String ?? ""
let uvPath = settings["CoulissesUV"] as? String ?? "uv"
let servicePath = settings["CoulissesPATH"] as? String ?? "/usr/bin:/bin:/usr/sbin:/sbin"
let isDev = settings["CoulissesVariante"] as? String == "dev"
/// « Coulisses (dév) » may run the service of a worktree of its repository, given at launch
/// by COULISSES_PROJET (`scripts/tester-branche.sh`): a branch is tried in the app itself,
/// still on Données-dev and port 8766. The published app never reads it.
let askedProject: String? = {
    guard isDev, let asked = ProcessInfo.processInfo.environment["COULISSES_PROJET"],
        !asked.isEmpty
    else { return nil }
    return URL(fileURLWithPath: NSString(string: asked).expandingTildeInPath)
        .resolvingSymlinksInPath().standardizedFileURL.path
}()
/// The project whose service runs: the installed repository, or one of its own worktrees
/// (`.claude/worktrees/<name>`); nil when the one asked is neither (said, never replaced).
let installedRoot = URL(fileURLWithPath: installedProject).resolvingSymlinksInPath()
    .standardizedFileURL.path
let projectDir: String? = {
    guard let asked = askedProject else { return installedProject }
    let root = installedRoot
    let worktrees = root + "/.claude/worktrees/"
    let isWorktree = asked.hasPrefix(worktrees) && !asked.dropFirst(worktrees.count).contains("/")
    return asked == root || isWorktree ? asked : nil
}()
let appName = settings["CFBundleName"] as? String ?? "Coulisses"
// The service's ports (cli.py): 8765 for the published app, 8766 for « Coulisses (dév) ».
let base = URL(string: isDev ? "http://127.0.0.1:8766/" : "http://127.0.0.1:8765/")!
let logDir = FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent("Library/Logs/Coulisses")
let logFile = logDir.appendingPathComponent(isDev ? "service-dev.log" : "service.log")
let startWithin: TimeInterval = 180
/// The data the service must serve: the real ones, or Données-dev for « Coulisses (dév) »,
/// unless told otherwise (the service refuses the real ones to dév).
let expectedData: String = {
    let given = ProcessInfo.processInfo.environment["COULISSES_DATA_DIR"]
    let path = given.map { NSString(string: $0).expandingTildeInPath }
        ?? FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(isDev ? "Coulisses/Données-dev" : "Coulisses/Données").path
    return path.precomposedStringWithCanonicalMapping
}()

struct Activity: Decodable {
    let recording: Bool
    let processing: Bool
    /// A model downloading (absent from a service older than this app: none).
    let downloading: Bool?
}

/// What the service says at /api/etat: enough to know it is Coulisses.
struct ServiceInfo: Decodable {
    let app_version: String
    let data_dir: String
    let pid: Int32
}

/// The parent of a process (1: nobody, its parent is gone).
func parentOf(_ pid: pid_t) -> pid_t? {
    var info = proc_bsdinfo()
    let size = Int32(MemoryLayout<proc_bsdinfo>.size)
    guard proc_pidinfo(pid, PROC_PIDTBSDINFO, 0, &info, size) == size else { return nil }
    return pid_t(info.pbi_ppid)
}

/// The processes a process started (the service under uv).
func childrenOf(_ pid: pid_t) -> [pid_t] {
    var children = [pid_t](repeating: 0, count: 64)
    let count = proc_listchildpids(
        pid, &children, Int32(children.count * MemoryLayout<pid_t>.size))
    return count > 0 ? Array(children.prefix(Int(count))) : []
}

func isAlive(_ pid: pid_t) -> Bool { kill(pid, 0) == 0 }

func nameOf(_ pid: pid_t) -> String {
    var buffer = [CChar](repeating: 0, count: 256)
    proc_name(pid, &buffer, UInt32(buffer.count))
    return String(cString: buffer)
}

/// A service nobody looks after: its parent (through uv) is gone. One started in a
/// Terminal has the Terminal's shell above it.
func isLeftAlone(_ pid: pid_t) -> Bool {
    var current = pid
    while let parent = parentOf(current) {
        if parent == 1 { return true }
        guard nameOf(parent) == "uv" else { return false }
        current = parent
    }
    return false
}

func appendToLog(_ line: String) {
    guard let handle = try? FileHandle(forWritingTo: logFile) else { return }
    handle.seekToEndOfFile()
    handle.write("\(line)\n".data(using: .utf8)!)
    try? handle.close()
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate,
    WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate
{
    var window: NSWindow!
    var web: WKWebView!
    /// The service this app started; nil when one was already running (left as it is).
    var service: Process?
    /// A service an earlier run of this app left alone (it was forced to quit, or crashed):
    /// taken back, so that ⌘Q stops it.
    var adopted: pid_t?
    var stopping = false
    /// The app is quitting: nothing more is shown (no update window on the way out).
    var quitting = false
    /// While a recording runs: its red dot and time in the menu bar, with its menu.
    var statusItem: NSStatusItem?
    /// What the menu was last built for (paused, the alert shown): rebuilt when it changes.
    var statusMenuFor: String?
    var recordingTimer: Timer?
    /// The recording shown, and when the service last answered about it.
    var shownSession: String?
    var lastAnswer = Date()
    var undecodedLogged = false
    /// The service's alerts already notified, by session and key: each one once.
    var notified: Set<String> = []
    var askedNotifications = false
    /// What the page reads (`notifications`): "allowed", "denied" or "unknown".
    var notificationStatus = "unknown"
    #if COULISSES_SPARKLE
        /// Sparkle (ADR 0040): only in the published app, built with its feed and its key.
        var updates: SPUStandardUpdaterController?
        /// A version found by a scheduled check, waiting for a click: the page shows a
        /// discreet « Mettre à jour » instead of Sparkle's window (gentle reminder).
        var updateReady = false
        /// The service's page said it shows that reminder (« rappel-mises-a-jour »), forgotten
        /// at each page change: otherwise Sparkle shows its own window, as before.
        var pageShowsReminder = false
        /// A version waits to be shown once the recording or processing is over: one wait.
        var withdrawalPending = false
    #endif

    func applicationDidFinishLaunching(_ notification: Notification) {
        setUpNotifications()
        watchRecording()
        startUpdates()
        buildMenu()
        makeWindow()
        showPage(title: "\(appName) démarre…", detail: nil, actions: false)
        start()
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows: Bool) -> Bool {
        window.makeKeyAndOrderFront(nil)
        return true
    }

    // -- the service --------------------------------------------------------------------

    func start() {
        guard projectDir != nil else {
            showPage(
                title: "Ce dossier n'est pas un worktree de Coulisses.",
                detail: "« \(askedProject ?? "") » n'est ni \(installedProject) ni l'un de ses worktrees (.claude/worktrees). Rien n'a été lancé.",
                actions: false)
            return
        }
        probe { info in
            if let info {
                self.open(info)
                return
            }
            if self.service?.isRunning == true {
                self.waitForService(since: Date())
                return
            }
            do {
                try self.launchService()
                self.waitForService(since: Date())
            } catch {
                self.showPage(
                    title: "Le service de Coulisses n'a pas pu démarrer.",
                    detail: "\(error.localizedDescription). Le détail est dans le journal.",
                    actions: true)
            }
        }
    }

    /// GET /api/etat: the service's facts, or nil if nothing (or something else) answers.
    func probe(_ done: @escaping (ServiceInfo?) -> Void) {
        var request = URLRequest(url: base.appendingPathComponent("api/etat"))
        request.timeoutInterval = 1
        URLSession.shared.dataTask(with: request) { data, response, _ in
            let ok = (response as? HTTPURLResponse)?.statusCode == 200
            let info = ok ? data.flatMap { try? JSONDecoder().decode(ServiceInfo.self, from: $0) } : nil
            DispatchQueue.main.async { done(info) }
        }.resume()
    }

    func launchService() throws {
        try FileManager.default.createDirectory(at: logDir, withIntermediateDirectories: true)
        if !FileManager.default.fileExists(atPath: logFile.path) {
            FileManager.default.createFile(atPath: logFile.path, contents: nil)
        }
        let log = try FileHandle(forWritingTo: logFile)
        log.seekToEndOfFile()
        log.write("\n===== Coulisses démarre le \(Date()) =====\n".data(using: .utf8)!)
        if !isStandalone, let projectDir, projectDir != installedProject {
            log.write("Projet : \(projectDir)\n".data(using: .utf8)!)
        }

        let process = Process()
        // Nothing inherited may change what runs: no injected library (DYLD_*), no other
        // Python (PYTHON*), in either mode.
        var environment = ProcessInfo.processInfo.environment.filter {
            !$0.key.hasPrefix("DYLD_") && !$0.key.hasPrefix("PYTHON")
                && $0.key != "COULISSES_PROJET"
        }
        if isStandalone {
            // Its own Python: -I takes nothing from the user's Python setup, -B writes
            // nothing into the .app; the engine's stages (without -I) are told the same.
            process.executableURL = bundledPython
            process.arguments = ["-I", "-B", "-u", "-m", "coulisses_app.cli", "--sans-navigateur"]
            process.currentDirectoryURL = FileManager.default.homeDirectoryForCurrentUser
            environment["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"  // its tools come first (bundle.py)
            environment["COULISSES_RESSOURCES"] = resourcesDir.path
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            environment["PYTHONNOUSERSITE"] = "1"
        } else {
            process.executableURL = URL(fileURLWithPath: uvPath)
            // Offline: uv never fetches anything when the app starts (P1).
            process.arguments =
                ["run", "--project", projectDir ?? "", "--offline", "coulisses-app", "--sans-navigateur"]
                + (isDev ? ["--dev"] : [])
            process.currentDirectoryURL = URL(fileURLWithPath: projectDir ?? "")
            environment["PATH"] = servicePath
            environment["PYTHONUNBUFFERED"] = "1"
        }
        process.environment = environment
        process.standardOutput = log
        process.standardError = log
        process.standardInput = FileHandle.nullDevice
        process.terminationHandler = { finished in
            DispatchQueue.main.async { self.serviceEnded(finished) }
        }
        try process.run()
        service = process
        // Which worktree runs, named only when this app started its service itself.
        if !isStandalone, let projectDir, projectDir != installedRoot {
            window.title = "\(appName) — \(URL(fileURLWithPath: projectDir).lastPathComponent)"
        }
    }

    /// The interface, once the service answers: only if it serves the expected data (a
    /// development service left running would show other sessions).
    func open(_ info: ServiceInfo) {
        let served = info.data_dir.precomposedStringWithCanonicalMapping
        guard served == expectedData else {
            showPage(
                title: "Un autre Coulisses tourne déjà, sur d'autres données.",
                detail: "Il utilise le dossier « \(served) ». Arrêtez-le (dans le Terminal : ⌃C), puis réessayez.",
                actions: true)
            return
        }
        if service == nil, adopted == nil, isLeftAlone(info.pid) {
            adopted = info.pid
        }
        refreshUpdatesState()
        forgetReminder()
        web.load(URLRequest(url: base))
    }

    func waitForService(since: Date) {
        probe { info in
            if let info {
                self.open(info)
                return
            }
            guard self.service?.isRunning == true else { return }  // said by serviceEnded
            if Date().timeIntervalSince(since) > startWithin {
                self.showPage(
                    title: "Le service de Coulisses ne répond pas.",
                    detail: "Il tourne depuis trois minutes sans répondre. Le détail est dans le journal.",
                    actions: true)
                return
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                self.waitForService(since: since)
            }
        }
    }

    func serviceEnded(_ process: Process) {
        if stopping || process !== service { return }
        service = nil
        appendToLog("===== le service s'est arrêté (code \(process.terminationStatus)) =====")
        showPage(
            title: "Le service de Coulisses s'est arrêté.",
            detail: "Ce qui était enregistré est gardé ; le détail est dans le journal.",
            actions: true)
    }

    /// Stops the service it started: as ⌃C would (the recording is closed, the stages
    /// stopped), then harder if it does not stop.
    func stopService(_ done: @escaping () -> Void) {
        let pid: pid_t
        if let process = service, process.isRunning {
            pid = process.processIdentifier
        } else if let adopted, isAlive(adopted) {
            pid = adopted
        } else {
            done()
            return
        }
        stopping = true
        kill(pid, SIGINT)
        DispatchQueue.global().async {
            func wait(_ seconds: Double) {
                let deadline = Date().addingTimeInterval(seconds)
                while isAlive(pid) && Date() < deadline { Thread.sleep(forTimeInterval: 0.1) }
            }
            wait(30)
            if isAlive(pid) {
                appendToLog("===== le service ne s'arrête pas : arrêté de force =====")
                let children = childrenOf(pid)
                kill(pid, SIGTERM)
                children.forEach { kill($0, SIGTERM) }
                wait(5)
                // uv and the service under it: none left running alone.
                for child in childrenOf(pid) + children where isAlive(child) { kill(child, SIGKILL) }
                if isAlive(pid) { kill(pid, SIGKILL) }
            }
            DispatchQueue.main.async(execute: done)
        }
    }

    // -- quitting -------------------------------------------------------------------------

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        let ours = service?.isRunning == true || adopted.map(isAlive) == true
        guard ours, !stopping else { return .terminateNow }
        var request = URLRequest(url: base.appendingPathComponent("api/activite"))
        request.timeoutInterval = 2
        URLSession.shared.dataTask(with: request) { data, _, _ in
            let activity = data.flatMap { try? JSONDecoder().decode(Activity.self, from: $0) }
            DispatchQueue.main.async { self.confirmQuit(activity) }
        }.resume()
        return .terminateLater
    }

    func confirmQuit(_ activity: Activity?) {
        var go = true
        if activity.map({ $0.recording || $0.processing || $0.downloading == true }) ?? true {
            let alert = NSAlert()
            if activity == nil {
                alert.messageText = "\(appName) ne répond pas."
                alert.informativeText =
                    "Un enregistrement ou un traitement est peut-être en cours. Quitter l'arrête ; ce qui est enregistré est gardé."
                alert.addButton(withTitle: "Quitter quand même")
            } else if activity?.recording == true {
                alert.messageText = "Un enregistrement est en cours."
                alert.informativeText = "Quitter l'arrête : ce qui est enregistré est gardé."
                alert.addButton(withTitle: "Arrêter et quitter")
            } else if activity?.processing != true {
                alert.messageText = "Un modèle est en cours de téléchargement."
                alert.informativeText =
                    "Il reprendra là où il en est la prochaine fois que vous le demanderez."
                alert.addButton(withTitle: "Quitter")
            } else {
                alert.messageText = "Un traitement est en cours."
                alert.informativeText =
                    "Il reprendra là où il en est au prochain lancement de Coulisses."
                    + (activity?.downloading == true
                        ? " Le téléchargement de modèle en cours reprendra aussi quand vous le demanderez."
                        : "")
                alert.addButton(withTitle: "Quitter")
            }
            alert.addButton(withTitle: "Annuler")
            go = alert.runModal() == .alertFirstButtonReturn
        }
        guard go else {
            NSApp.reply(toApplicationShouldTerminate: false)
            return
        }
        quitting = true
        showPage(title: "\(appName) s'arrête…", detail: nil, actions: false)
        stopService { NSApp.reply(toApplicationShouldTerminate: true) }
    }

    /// Closing the window hides it; the app (and the service) stay until ⌘Q.
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        window.orderOut(nil)
        return false
    }

    // -- the window -----------------------------------------------------------------------

    func makeWindow() {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        // Its lists would be fetched from the network (P1): the window only shows 127.0.0.1.
        configuration.preferences.isFraudulentWebsiteWarningEnabled = false
        addBridge(to: configuration.userContentController)
        web = WKWebView(frame: .zero, configuration: configuration)
        web.navigationDelegate = self
        web.uiDelegate = self
        web.allowsBackForwardNavigationGestures = false
        // Safari's inspector runs any script in the page: in the development app only.
        web.isInspectable = isDev
        web.setValue(false, forKey: "drawsBackground")

        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1440, height: 900),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered, defer: false)
        window.title = appName
        window.minSize = NSSize(width: 900, height: 600)
        window.contentView = web
        window.delegate = self
        window.backgroundColor = NSColor(name: nil) { appearance in
            appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
                ? NSColor(red: 0x13 / 255, green: 0x13 / 255, blue: 0x13 / 255, alpha: 1)
                : NSColor(red: 0xfa / 255, green: 0xfa / 255, blue: 0xfa / 255, alpha: 1)
        }
        window.center()
        window.setFrameAutosaveName(appName)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    /// While the service starts, or when it cannot: a plain page, said in French.
    func showPage(title: String, detail: String?, actions: Bool) {
        reminderWithdrawn()
        let escape = { (text: String) in
            text.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;")
        }
        let buttons =
            actions
            ? """
            <p class="actions"><a href="coulisses://relancer">Réessayer</a>
            <a href="coulisses://journal">Ouvrir le journal</a></p>
            """ : ""
        let html = """
            <!doctype html><html lang="fr"><head><meta charset="utf-8"><style>
            :root { color-scheme: light dark; --bg: #fafafa; --fg: #1d1d1f; --muted: #6b6b6b; --accent: #a63d1e; }
            @media (prefers-color-scheme: dark) { :root { --bg: #131313; --fg: #ededed; --muted: #a3a3a3; --accent: #ec9a78; } }
            body { margin: 0; height: 100vh; display: grid; place-content: center; text-align: center;
              background: var(--bg); color: var(--fg); font: 15px -apple-system, sans-serif; }
            h1 { font-weight: 500; font-size: 22px; letter-spacing: -0.02em; margin: 0 0 8px; }
            p { color: var(--muted); max-width: 46ch; margin: 0 auto; line-height: 1.5; }
            .actions { margin-top: 20px; display: flex; gap: 16px; justify-content: center; }
            a { color: var(--accent); text-decoration: none; font-weight: 500; }
            </style></head><body><h1>\(escape(title))</h1>
            \(detail.map { "<p>\(escape($0))</p>" } ?? "")\(buttons)</body></html>
            """
        web.loadHTMLString(html, baseURL: nil)
    }

    // -- what the page asks of the window -------------------------------------------------

    /// A new page (a reload, a navigation) has not said yet whether it shows the update
    /// reminder: until it does, Sparkle shows its own window.
    func webView(_ webView: WKWebView, didCommit navigation: WKNavigation!) {
        pageChanged()
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        reminderWithdrawn()
    }

    func webView(
        _ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
        decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
    ) {
        guard let url = action.request.url else { return decisionHandler(.cancel) }
        if url.scheme == "coulisses" {
            decisionHandler(.cancel)
            if url.host == "relancer" {
                showPage(title: "\(appName) démarre…", detail: nil, actions: false)
                start()
            } else if url.host == "journal" {
                NSWorkspace.shared.open(logFile)
            }
            return
        }
        // Only the service, and the launcher's own pages (loaded without a base URL), show in
        // this window: not another port of this Mac (Ollama…), nor data:, blob:, file:.
        let isService = url.scheme == "http" && url.host == base.host && url.port == base.port
        if isService {
            return decisionHandler(action.shouldPerformDownload ? .download : .allow)
        }
        if url.absoluteString == "about:blank" { return decisionHandler(.allow) }
        // Anything else on the web opens in the browser (a model's terms); the rest, nowhere.
        if url.scheme == "http" || url.scheme == "https" { NSWorkspace.shared.open(url) }
        decisionHandler(.cancel)
    }

    func webView(
        _ webView: WKWebView, decidePolicyFor response: WKNavigationResponse,
        decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void
    ) {
        let disposition =
            (response.response as? HTTPURLResponse)?.value(forHTTPHeaderField: "Content-Disposition") ?? ""
        if disposition.lowercased().hasPrefix("attachment") || !response.canShowMIMEType {
            return decisionHandler(.download)
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = self
    }

    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
        download.delegate = self
    }

    /// An export: saved where the user says, under the name the service gave it.
    func download(
        _ download: WKDownload, decideDestinationUsing response: URLResponse,
        suggestedFilename: String, completionHandler: @escaping (URL?) -> Void
    ) {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = suggestedFilename
        panel.directoryURL = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first
        panel.beginSheetModal(for: window) { answer in
            completionHandler(answer == .OK ? panel.url : nil)
        }
    }

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        let alert = NSAlert()
        alert.messageText = "L'export n'a pas pu être enregistré."
        alert.informativeText = error.localizedDescription
        alert.runModal()
    }

    /// « Choisir un fichier »: the Finder's window.
    func webView(
        _ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
        initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void
    ) {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.canChooseDirectories = parameters.allowsDirectories
        panel.beginSheetModal(for: window) { answer in
            completionHandler(answer == .OK ? panel.urls : nil)
        }
    }

    func webView(
        _ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
        initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void
    ) {
        let alert = NSAlert()
        alert.messageText = message
        alert.runModal()
        completionHandler()
    }

    func webView(
        _ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
        initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void
    ) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "OK")
        alert.addButton(withTitle: "Annuler")
        completionHandler(alert.runModal() == .alertFirstButtonReturn)
    }

    // -- the menu -------------------------------------------------------------------------

    func buildMenu() {
        let bar = NSMenu()
        func menu(_ title: String, _ items: [NSMenuItem]) {
            let holder = NSMenuItem()
            let submenu = NSMenu(title: title)
            items.forEach(submenu.addItem)
            holder.submenu = submenu
            bar.addItem(holder)
        }
        func item(_ title: String, _ action: Selector?, _ key: String, _ modifiers: NSEvent.ModifierFlags = .command) -> NSMenuItem {
            let made = NSMenuItem(title: title, action: action, keyEquivalent: key)
            made.keyEquivalentModifierMask = modifiers
            return made
        }
        menu(appName, [
            item("À propos de \(appName)", #selector(NSApplication.orderFrontStandardAboutPanel(_:)), ""),
            .separator(),
            item("Masquer \(appName)", #selector(NSApplication.hide(_:)), "h"),
            item("Masquer les autres", #selector(NSApplication.hideOtherApplications(_:)), "h", [.command, .option]),
            item("Tout afficher", #selector(NSApplication.unhideAllApplications(_:)), ""),
            .separator(),
            item("Quitter \(appName)", #selector(NSApplication.terminate(_:)), "q"),
        ])
        menu("Édition", [
            item("Annuler", Selector(("undo:")), "z"),
            item("Rétablir", Selector(("redo:")), "z", [.command, .shift]),
            .separator(),
            item("Couper", #selector(NSText.cut(_:)), "x"),
            item("Copier", #selector(NSText.copy(_:)), "c"),
            item("Coller", #selector(NSText.paste(_:)), "v"),
            item("Tout sélectionner", #selector(NSText.selectAll(_:)), "a"),
        ])
        menu("Présentation", [
            item("Recharger", #selector(WKWebView.reload(_:)), "r"),
        ])
        let windowItems = [
            item("Réduire", #selector(NSWindow.performMiniaturize(_:)), "m"),
            item("Fermer", #selector(NSWindow.performClose(_:)), "w"),
        ]
        menu("Fenêtre", windowItems)
        if let check = updatesMenuItem() {
            bar.items.first?.submenu?.insertItem(check, at: 1)
        }
        NSApp.mainMenu = bar
        NSApp.windowsMenu = bar.items.last?.submenu
    }
}

// -- what the page reads from the app, and asks of it -----------------------------------------

extension AppDelegate: WKScriptMessageHandler {
    /// `window.coulissesApp` (web/src/appBridge.ts): the notifications' permission, and in the
    /// published app its updates (ADR 0040, 0051).
    func addBridge(to content: WKUserContentController) {
        content.add(self, name: "coulisses")
        refreshBridge(content)
    }

    func refreshBridge(_ given: WKUserContentController? = nil) {
        guard let content = given ?? web?.configuration.userContentController else { return }
        var state: [String: Any] = ["notifications": notificationStatus]
        if let updates = updatesBridgeState() { state["updates"] = updates }
        let json =
            (try? JSONSerialization.data(withJSONObject: state)).flatMap {
                String(data: $0, encoding: .utf8)
            } ?? "{}"
        // For the next page load, and told to the page already shown (appBridge.ts).
        content.removeAllUserScripts()
        content.addUserScript(
            WKUserScript(
                source: "window.coulissesApp = \(json);",
                injectionTime: .atDocumentStart, forMainFrameOnly: true))
        web?.evaluateJavaScript(
            "window.coulissesApp = \(json);"
                + " window.dispatchEvent(new Event('coulisses:mises-a-jour'));")
    }

    func userContentController(
        _ controller: WKUserContentController, didReceive message: WKScriptMessage
    ) {
        // Only from the service's page, never from another origin.
        let origin = message.frameInfo.securityOrigin
        guard message.frameInfo.isMainFrame, origin.host == base.host, origin.port == base.port ?? 0,
            let body = message.body as? [String: Any], let action = body["action"] as? String,
            handleUpdateMessage(action, body)
        else { return }
        refreshBridge()
    }
}

// -- the recording, seen from outside the window -------------------------------------------
//
// While a recording runs, a red dot and its time stay in the menu bar, with Pause/Reprendre,
// Arrêter and Ouvrir Coulisses; the service's alerts (a long silence, a set duration) become
// notifications with Arrêter and Continuer. The service decides the alerts and words them
// (its settings, its tests); the app shows each one once. Nothing ever stops by itself.

struct RecordingAlert: Decodable {
    let key: String
    let title: String
    let text: String
}

/// GET /api/enregistrement: what the menu bar needs (an older service has no `alert`).
struct RecordingNow: Decodable {
    let session_id: String
    let state: String
    let elapsed_s: Double
    let alert: RecordingAlert?
}

func clock(_ seconds: Double) -> String {
    let total = Int(seconds)
    let (h, m, s) = (total / 3600, total / 60 % 60, total % 60)
    return h > 0 ? String(format: "%d:%02d:%02d", h, m, s) : String(format: "%02d:%02d", m, s)
}

extension AppDelegate: UNUserNotificationCenterDelegate {
    func setUpNotifications() {
        let center = UNUserNotificationCenter.current()
        center.delegate = self
        let stop = UNNotificationAction(identifier: "arreter", title: "Arrêter", options: [])
        let keep = UNNotificationAction(identifier: "continuer", title: "Continuer", options: [])
        center.setNotificationCategories([
            UNNotificationCategory(
                identifier: "enregistrement", actions: [stop, keep], intentIdentifiers: [], options: [])
        ])
        readNotificationStatus()
    }

    func applicationDidBecomeActive(_ notification: Notification) {
        readNotificationStatus()  // changed in Réglages Système meanwhile
    }

    func readNotificationStatus() {
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            let status: String
            switch settings.authorizationStatus {
            case .authorized, .provisional: status = "allowed"
            case .denied: status = "denied"
            default: status = "unknown"
            }
            DispatchQueue.main.async {
                self.notificationStatus = status
                self.refreshBridge()
            }
        }
    }

    /// Asked at the first recording, not at launch.
    func askNotificationsOnce() {
        guard !askedNotifications else { return }
        askedNotifications = true
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, error in
            if let error { appendToLog("notifications : \(error.localizedDescription)") }
            self.readNotificationStatus()
        }
    }

    func watchRecording() { scheduleWatch(after: 2) }

    /// Every second while recording, every two otherwise: 127.0.0.1 only.
    func scheduleWatch(after seconds: TimeInterval) {
        recordingTimer?.invalidate()
        recordingTimer = Timer.scheduledTimer(withTimeInterval: seconds, repeats: false) {
            [weak self] _ in self?.pollRecording()
        }
    }

    func pollRecording() {
        var request = URLRequest(url: base.appendingPathComponent("api/enregistrement"))
        request.timeoutInterval = 2
        URLSession.shared.dataTask(with: request) { data, response, _ in
            let answered = (response as? HTTPURLResponse)?.statusCode == 200
            let body = data.map { String(decoding: $0, as: UTF8.self).trimmingCharacters(in: .whitespaces) }
            let now = answered ? data.flatMap { try? JSONDecoder().decode(RecordingNow.self, from: $0) } : nil
            DispatchQueue.main.async {
                if answered && body == "null" {
                    self.lastAnswer = Date()
                    self.showRecording(nil)  // nothing records
                } else if let now {
                    self.lastAnswer = Date()
                    self.showRecording(now)
                } else if answered {
                    // Something this app cannot read: never taken for « nothing records ».
                    if !self.undecodedLogged {
                        self.undecodedLogged = true
                        appendToLog("barre des menus : réponse illisible de /api/enregistrement : \(body ?? "")")
                    }
                } else if self.statusItem != nil, Date().timeIntervalSince(self.lastAnswer) > 8 {
                    // A busy service is not a stopped recording: said, nothing stopped.
                    self.statusItem?.button?.attributedTitle = NSAttributedString(
                        string: "◯ \(appName) ne répond pas")
                }
                self.scheduleWatch(after: self.statusItem == nil ? 2 : 1)
            }
        }.resume()
    }

    func showRecording(_ now: RecordingNow?) {
        guard let now, !quitting else {
            if let statusItem { NSStatusBar.system.removeStatusItem(statusItem) }
            statusItem = nil
            statusMenuFor = nil
            if let ended = shownSession {
                // Its reminders are of no use any more: « Arrêter » must not act on another.
                let ids = notified.filter { $0.hasPrefix(ended + "|") }
                UNUserNotificationCenter.current().removeDeliveredNotifications(withIdentifiers: Array(ids))
            }
            shownSession = nil
            return
        }
        shownSession = now.session_id
        if statusItem == nil {
            statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
            askNotificationsOnce()
        }
        let paused = now.state == "paused"
        let title = NSMutableAttributedString(
            string: paused ? "◯ " : "● ",
            attributes: [.foregroundColor: paused ? NSColor.secondaryLabelColor : NSColor.systemRed])
        title.append(
            NSAttributedString(
                string: (isDev ? "dév " : "") + clock(now.elapsed_s) + (paused ? " en pause" : ""),
                attributes: [.font: NSFont.monospacedDigitSystemFont(ofSize: 0, weight: .regular)]))
        statusItem?.button?.attributedTitle = title
        let menuFor = "\(paused)|\(now.alert?.key ?? "")"
        if statusMenuFor != menuFor {
            statusMenuFor = menuFor
            let menu = NSMenu()
            if let alert = now.alert {
                // Seen here too, notifications allowed or not.
                let line = NSMenuItem(title: alert.title, action: nil, keyEquivalent: "")
                line.isEnabled = false
                menu.addItem(line)
                menu.addItem(.separator())
            }
            menu.addItem(
                NSMenuItem(
                    title: paused ? "Reprendre" : "Pause",
                    action: paused ? #selector(resumeRecording) : #selector(pauseRecording), keyEquivalent: ""))
            menu.addItem(
                NSMenuItem(title: "Arrêter l'enregistrement", action: #selector(stopRecording), keyEquivalent: ""))
            menu.addItem(.separator())
            menu.addItem(NSMenuItem(title: "Ouvrir \(appName)", action: #selector(openWindow), keyEquivalent: ""))
            menu.items.forEach { $0.target = self }
            statusItem?.menu = menu
        }
        if let alert = now.alert { notify(alert, session: now.session_id) }
    }

    func notify(_ alert: RecordingAlert, session: String) {
        let id = "\(session)|\(alert.key)"
        guard notified.insert(id).inserted else { return }
        if notificationStatus == "denied" {
            appendToLog("rappel non montré, notifications refusées : \(alert.title)")
            return
        }
        let content = UNMutableNotificationContent()
        content.title = alert.title
        content.body = alert.text
        content.sound = .default
        content.categoryIdentifier = "enregistrement"
        UNUserNotificationCenter.current().add(
            UNNotificationRequest(identifier: id, content: content, trigger: nil)
        ) { error in
            if let error { appendToLog("rappel non montré : \(error.localizedDescription)") }
        }
    }

    /// Shown even when Coulisses is in front: the reminder is the point.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter, willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .list, .sound])
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let session = String(response.notification.request.identifier.split(separator: "|").first ?? "")
        switch response.actionIdentifier {
        case "arreter": stopIfStill(session)
        case "continuer": break  // the service does not raise the same alert again
        default: openWindow()
        }
        completionHandler()
    }

    /// « Arrêter » from a reminder: only the recording it was about, never another one.
    func stopIfStill(_ session: String) {
        var request = URLRequest(url: base.appendingPathComponent("api/enregistrement"))
        request.timeoutInterval = 5
        URLSession.shared.dataTask(with: request) { data, _, _ in
            let now = data.flatMap { try? JSONDecoder().decode(RecordingNow.self, from: $0) }
            DispatchQueue.main.async {
                if now?.session_id == session {
                    self.stopRecording()
                } else {
                    let alert = NSAlert()
                    alert.messageText = "Cet enregistrement est déjà terminé."
                    alert.informativeText = "Rien n'a été arrêté."
                    NSApp.activate(ignoringOtherApps: true)
                    alert.runModal()
                }
            }
        }.resume()
    }

    @objc func pauseRecording() { send("api/enregistrement/pause", failing: "La pause n'a pas pu être faite.") }
    @objc func resumeRecording() { send("api/enregistrement/reprise", failing: "L'enregistrement n'a pas pu reprendre.") }
    @objc func stopRecording() { send("api/enregistrement/arret", failing: "L'enregistrement n'a pas pu être arrêté.") }

    @objc func openWindow() {
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    /// The service's own routes, as the page uses them; a failure is said, never silent.
    func send(_ path: String, failing: String) {
        var request = URLRequest(url: base.appendingPathComponent(path))
        request.httpMethod = "POST"
        request.timeoutInterval = 30
        URLSession.shared.dataTask(with: request) { data, response, error in
            let code = (response as? HTTPURLResponse)?.statusCode ?? 0
            let detail =
                data.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }?["detail"]
                as? String
            DispatchQueue.main.async {
                if (200..<300).contains(code) {
                    self.pollRecording()
                    return
                }
                let alert = NSAlert()
                alert.messageText = failing
                alert.informativeText = detail ?? error?.localizedDescription ?? "Coulisses ne répond pas (code \(code))."
                NSApp.activate(ignoringOtherApps: true)
                alert.runModal()
            }
        }.resume()
    }
}

// -- updates (ADR 0040) ---------------------------------------------------------------------

#if COULISSES_SPARKLE
    extension AppDelegate: SPUUpdaterDelegate, SPUStandardUserDriverDelegate {
        /// Sparkle looks for updates only after the user's consent (it asks on the second
        /// launch) or on demand; nothing downloads nor installs without a click (Info.plist:
        /// no automatic updates, no system profile). The development app has no updater.
        func startUpdates() {
            guard isStandalone, !isDev, settings["SUFeedURL"] != nil, settings["SUPublicEDKey"] != nil
            else { return }
            updates = SPUStandardUpdaterController(
                startingUpdater: true, updaterDelegate: self, userDriverDelegate: self)
        }

        func updatesMenuItem() -> NSMenuItem? {
            guard updates != nil else { return nil }
            let check = NSMenuItem(
                title: "Rechercher les mises à jour…", action: #selector(checkNow), keyEquivalent: "")
            check.target = self
            return check
        }

        /// The menu and the page's buttons. A version already found (the reminder) skips
        /// `shouldProceedWithUpdate`: refused here while a recording or a processing runs,
        /// said in French; the reminder stays.
        @objc func checkNow() {
            guard let updates else { return }
            if updateReady, let busy = busyNow() {
                let alert = NSAlert()
                alert.messageText = "La mise à jour attendra."
                alert.informativeText =
                    "\(busy) : cliquez de nouveau sur « Mettre à jour » une fois qu'il sera fini."
                alert.runModal()
                return
            }
            updates.checkForUpdates(nil)
        }

        func forgetReminder() { pageShowsReminder = false }

        /// Nothing shows the reminder any more (the page withdrew it, a launcher page, the
        /// page's process gone): a version already waiting is shown in Sparkle's window, at
        /// once or once the recording or processing is over, unless a page shows it again.
        func reminderWithdrawn() {
            pageShowsReminder = false
            guard updateReady, !quitting, !withdrawalPending else { return }
            let show = { [weak self] in
                guard let self else { return }
                self.withdrawalPending = false
                guard !self.quitting, !self.pageShowsReminder, self.updateReady else { return }
                self.updates?.checkForUpdates(nil)
            }
            withdrawalPending = true
            if busyNow() == nil { show() } else { waitUntilIdle(then: show) }
        }

        /// A new page says again that it shows the reminder once mounted; one that never
        /// does (a broken page) within 10 s counts as a withdrawal.
        func pageChanged() {
            forgetReminder()
            guard updateReady else { return }
            DispatchQueue.main.asyncAfter(deadline: .now() + 10) { [weak self] in
                guard let self, !self.pageShowsReminder else { return }
                self.reminderWithdrawn()
            }
        }

        /// The updates' part of what the page reads (web/src/appBridge.ts).
        func updatesBridgeState() -> [String: Any]? {
            guard let updater = updates?.updater else { return nil }
            return [
                "ready": updateReady,
                "automatic": updater.automaticallyChecksForUpdates,
                "lastCheck": updater.lastUpdateCheckDate.map { ISO8601DateFormatter().string(from: $0) }
                    ?? NSNull(),
            ]
        }

        func refreshUpdatesState() { refreshBridge() }

        // A version found by a scheduled check is not shown in Sparkle's window when the
        // service's page shows the reminder (it said so): its « Mettre à jour » is the
        // reminder, and its click (« rechercher-mises-a-jour ») brings Sparkle's window with
        // that version. Otherwise (a launcher page, an older page), Sparkle's window opens, so
        // that no version found is ever hidden. Checks asked by the user show it at once.
        var supportsGentleScheduledUpdateReminders: Bool { true }

        func standardUserDriverShouldHandleShowingScheduledUpdate(
            _ update: SUAppcastItem, andInImmediateFocus immediateFocus: Bool
        ) -> Bool { !pageShowsReminder }

        func standardUserDriverWillHandleShowingUpdate(
            _ handleShowingUpdate: Bool, forUpdate update: SUAppcastItem, state: SPUUserUpdateState
        ) {
            guard !handleShowingUpdate else { return }
            updateReady = true
            refreshUpdatesState()
        }

        /// Seen in Sparkle's window (installed, skipped or left for later): no more reminder.
        func standardUserDriverDidReceiveUserAttention(forUpdate update: SUAppcastItem) {
            updateReady = false
            refreshUpdatesState()
        }

        func standardUserDriverWillFinishUpdateSession() {
            updateReady = false
            refreshUpdatesState()
        }

        /// The page's requests about updates; false for any other.
        func handleUpdateMessage(_ action: String, _ body: [String: Any]) -> Bool {
            guard let updates else { return false }
            switch action {
            case "mises-a-jour-automatiques":
                if let on = body["value"] as? Bool { updates.updater.automaticallyChecksForUpdates = on }
            case "rechercher-mises-a-jour":
                checkNow()
            case "rappel-mises-a-jour":
                // Said once when shown, and withdrawn (false) when it no longer is.
                if body["value"] as? Bool ?? true { pageShowsReminder = true } else { reminderWithdrawn() }
            default:
                return false
            }
            return true
        }

        /// What the service is doing (GET /api/activite): said if it records or processes.
        /// Ours running without answering counts as busy, as when quitting; nil when no
        /// service runs at all (an update may be what repairs it).
        func busyNow() -> String? {
            var request = URLRequest(url: base.appendingPathComponent("api/activite"))
            request.timeoutInterval = 2
            let answered = DispatchSemaphore(value: 0)
            var activity: Activity?
            URLSession.shared.dataTask(with: request) { data, _, _ in
                activity = data.flatMap { try? JSONDecoder().decode(Activity.self, from: $0) }
                answered.signal()
            }.resume()
            _ = answered.wait(timeout: .now() + 3)
            guard let activity else {
                let ours = service?.isRunning == true || adopted.map(isAlive) == true
                return ours ? "Coulisses ne répond pas, un enregistrement est peut-être en cours" : nil
            }
            if activity.recording { return "Un enregistrement est en cours" }
            if activity.processing { return "Un traitement est en cours" }
            return nil
        }

        /// Never during a recording or a processing: a version found then is not even shown,
        /// so not downloaded (a chain must not mix two versions of the engine, P5 and P7); one
        /// already found waits behind `checkNow`.
        func updater(
            _ updater: SPUUpdater, shouldProceedWithUpdate updateItem: SUAppcastItem,
            updateCheck: SPUUpdateCheck
        ) throws {
            if let busy = busyNow() {
                throw NSError(
                    domain: "Coulisses", code: 1,
                    userInfo: [
                        NSLocalizedDescriptionKey:
                            "\(busy) : la mise à jour attendra qu'il soit fini. Cherchez-la de nouveau ensuite."
                    ])
            }
        }

        /// One started meanwhile: the relaunch waits for its end.
        func updater(
            _ updater: SPUUpdater, shouldPostponeRelaunchForUpdate item: SUAppcastItem,
            untilInvokingBlock installHandler: @escaping () -> Void
        ) -> Bool {
            guard let busy = busyNow() else { return false }
            let alert = NSAlert()
            alert.messageText = "La mise à jour est prête."
            alert.informativeText = "\(busy) : elle s'installera dès qu'il sera fini."
            alert.runModal()
            waitUntilIdle(then: installHandler)
            return true
        }

        func waitUntilIdle(then go: @escaping () -> Void) {
            DispatchQueue.main.asyncAfter(deadline: .now() + 30) {
                if self.busyNow() == nil { go() } else { self.waitUntilIdle(then: go) }
            }
        }

        func updater(
            _ updater: SPUUpdater, didFinishUpdateCycleFor updateCheck: SPUUpdateCheck, error: Error?
        ) {
            refreshUpdatesState()
        }
    }
#else
    extension AppDelegate {
        func startUpdates() {}
        func updatesMenuItem() -> NSMenuItem? { nil }
        func updatesBridgeState() -> [String: Any]? { nil }
        func handleUpdateMessage(_ action: String, _ body: [String: Any]) -> Bool { false }
        func refreshUpdatesState() { refreshBridge() }
        func forgetReminder() {}
        func reminderWithdrawn() {}
        func pageChanged() {}
    }
#endif

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
