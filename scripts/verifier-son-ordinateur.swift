// Checks, after a macOS update, that the app can still read and ask the permission to capture
// the computer's sound (ADR 0077): TCC's private calls must be there and answer as before.
// Usage: swift scripts/verifier-son-ordinateur.swift ; exits 1 if they changed.
// It reads the permission of whatever runs it (the Terminal here): only the calls are checked.

import Foundation

let path = "/System/Library/PrivateFrameworks/TCC.framework/Versions/A/TCC"
let version = ProcessInfo.processInfo.operatingSystemVersionString
guard let tcc = dlopen(path, RTLD_NOW) else {
    print("ÉCHEC : macOS \(version) n'a plus TCC.framework : la page ne saura plus si le son de l'ordinateur est autorisé.")
    exit(1)
}
typealias Preflight = @convention(c) (CFString, CFDictionary?) -> Int32
guard let preflightSymbol = dlsym(tcc, "TCCAccessPreflight"), dlsym(tcc, "TCCAccessRequest") != nil else {
    print("ÉCHEC : macOS \(version) n'a plus TCCAccessPreflight ou TCCAccessRequest.")
    exit(1)
}
let answer = unsafeBitCast(preflightSymbol, to: Preflight.self)("kTCCServiceAudioCapture" as CFString, nil)
guard [0, 1, 2].contains(answer) else {
    print("ÉCHEC : sous macOS \(version), TCCAccessPreflight répond \(answer), une valeur inconnue.")
    exit(1)
}
print("Son de l'ordinateur : les appels de TCC répondent comme avant sous macOS \(version) (\(["autorisé", "refusé", "pas encore demandé"][Int(answer)]) pour ce qui lance la vérification).")
