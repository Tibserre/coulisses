// The Mac's microphone and the computer's sound, recorded together (ADR 0032).
//
// macOS taps everything the computer plays (a process tap: Zoom, Teams, a meeting in the
// browser…) and puts it beside the microphone in a private aggregate device whose clock is
// the microphone's: the tap is resampled to it (drift compensation), so the two tracks
// never drift apart. Nothing is processed: no echo cancelling, no gain, no noise reduction.
//
// Usage: coulisses-son-ordinateur --micro <name> --canaux <n> --frequence <hz>
// stdout: blocks, each an 8-byte header (UInt32 frames, UInt32 frames lost just before it,
//         little-endian) then its float32 little-endian frames, interleaved: the
//         microphone's first <n> channels, then the computer's sound (mono).
// stderr: one JSON object per line: {"event":"ready",...}, {"event":"waiting",...},
//         {"event":"error","code":...,"detail":...}.
// It stops, cleanly, when its standard input closes or on SIGTERM.

import AudioToolbox
import CoreAudio
import Foundation

struct Failure: Error {
    let code: String
    let detail: String
}

func say(_ object: [String: Any]) {
    guard let data = try? JSONSerialization.data(withJSONObject: object),
        var line = String(data: data, encoding: .utf8)
    else { return }
    line += "\n"
    FileHandle.standardError.write(line.data(using: .utf8)!)
}

func check(_ status: OSStatus, _ code: String, _ what: String) throws {
    if status != noErr {
        throw Failure(code: code, detail: "\(what): OSStatus \(status)")
    }
}

func address(
    _ selector: AudioObjectPropertySelector,
    _ scope: AudioObjectPropertyScope = kAudioObjectPropertyScopeGlobal
) -> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(
        mSelector: selector, mScope: scope, mElement: kAudioObjectPropertyElementMain)
}

func stringProperty(_ object: AudioObjectID, _ selector: AudioObjectPropertySelector) -> String? {
    var where_ = address(selector)
    var value: Unmanaged<CFString>?
    var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
    guard AudioObjectGetPropertyData(object, &where_, 0, nil, &size, &value) == noErr else {
        return nil
    }
    return value?.takeRetainedValue() as String?
}

func allDevices() throws -> [AudioObjectID] {
    var where_ = address(kAudioHardwarePropertyDevices)
    var size: UInt32 = 0
    try check(
        AudioObjectGetPropertyDataSize(
            AudioObjectID(kAudioObjectSystemObject), &where_, 0, nil, &size),
        "micro_introuvable", "listing the devices")
    var ids = [AudioObjectID](repeating: 0, count: Int(size) / MemoryLayout<AudioObjectID>.size)
    try check(
        AudioObjectGetPropertyData(
            AudioObjectID(kAudioObjectSystemObject), &where_, 0, nil, &size, &ids),
        "micro_introuvable", "listing the devices")
    return ids
}

/// The channels of each input stream of a device, in the order its I/O gives them.
func inputLayout(_ device: AudioObjectID) throws -> [Int] {
    var where_ = address(kAudioDevicePropertyStreamConfiguration, kAudioObjectPropertyScopeInput)
    var size: UInt32 = 0
    try check(
        AudioObjectGetPropertyDataSize(device, &where_, 0, nil, &size),
        "format", "reading the input configuration")
    let raw = UnsafeMutableRawPointer.allocate(
        byteCount: Int(size), alignment: MemoryLayout<AudioBufferList>.alignment)
    defer { raw.deallocate() }
    try check(
        AudioObjectGetPropertyData(device, &where_, 0, nil, &size, raw),
        "format", "reading the input configuration")
    let list = UnsafeMutableAudioBufferListPointer(raw.assumingMemoryBound(to: AudioBufferList.self))
    return list.map { Int($0.mNumberChannels) }
}

func inputStreamsAreFloat(_ device: AudioObjectID) throws -> Bool {
    var where_ = address(kAudioDevicePropertyStreams, kAudioObjectPropertyScopeInput)
    var size: UInt32 = 0
    try check(
        AudioObjectGetPropertyDataSize(device, &where_, 0, nil, &size), "format",
        "listing the streams")
    var streams = [AudioStreamID](
        repeating: 0, count: Int(size) / MemoryLayout<AudioStreamID>.size)
    try check(
        AudioObjectGetPropertyData(device, &where_, 0, nil, &size, &streams), "format",
        "listing the streams")
    for stream in streams {
        var format = AudioStreamBasicDescription()
        var formatSize = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
        var formatWhere = address(kAudioStreamPropertyVirtualFormat)
        try check(
            AudioObjectGetPropertyData(stream, &formatWhere, 0, nil, &formatSize, &format),
            "format", "reading a stream's format")
        let isFloat = format.mFormatFlags & kAudioFormatFlagIsFloat != 0
        let interleaved = format.mFormatFlags & kAudioFormatFlagIsNonInterleaved == 0
        if format.mFormatID != kAudioFormatLinearPCM || !isFloat || format.mBitsPerChannel != 32
            || !interleaved
        {
            return false
        }
    }
    return true
}

// -- arguments ------------------------------------------------------------------------------

var micName: String?
var wanted = 1
var rate = 48_000.0
var arguments = CommandLine.arguments.dropFirst().makeIterator()
while let argument = arguments.next() {
    switch argument {
    case "--micro": micName = arguments.next()
    case "--canaux": wanted = Int(arguments.next() ?? "") ?? 0
    case "--frequence": rate = Double(arguments.next() ?? "") ?? 0
    default:
        say(["event": "error", "code": "arguments", "detail": "unknown argument \(argument)"])
        exit(2)
    }
}
guard let micName, wanted >= 1, rate > 0 else {
    say(["event": "error", "code": "arguments", "detail": "--micro, --canaux, --frequence"])
    exit(2)
}

// -- the tap and the aggregate device -------------------------------------------------------

var tapID = AudioObjectID(kAudioObjectUnknown)
var aggregateID = AudioObjectID(kAudioObjectUnknown)
var procID: AudioDeviceIOProcID?

func tearDown() {
    if let procID {
        AudioDeviceStop(aggregateID, procID)
        AudioDeviceDestroyIOProcID(aggregateID, procID)
    }
    if aggregateID != kAudioObjectUnknown {
        AudioHardwareDestroyAggregateDevice(aggregateID)
    }
    if tapID != kAudioObjectUnknown {
        AudioHardwareDestroyProcessTap(tapID)
    }
}

let output = FileHandle.standardOutput
let writing = DispatchQueue(label: "coulisses.son-ordinateur.write")
var micChannels: [Int] = []
var micStreams = 0
var expected: Float64 = -1
var actualRate: Float64 = 0
var announced = false
var calls = 0
var lastTapBytes: UInt32 = 0

func start() throws {
    let devices = try allDevices()
    guard
        let mic = devices.first(where: {
            stringProperty($0, kAudioObjectPropertyName) == micName
                && ((try? inputLayout($0).reduce(0, +)) ?? 0) > 0
        }),
        let micUID = stringProperty(mic, kAudioDevicePropertyDeviceUID)
    else {
        throw Failure(code: "micro_introuvable", detail: micName)
    }

    // Everything the computer plays, mixed down to one channel; heard as it is (unmuted).
    let description = CATapDescription(monoGlobalTapButExcludeProcesses: [])
    description.uuid = UUID()
    description.name = "Coulisses"
    description.isPrivate = true
    description.muteBehavior = .unmuted
    try check(AudioHardwareCreateProcessTap(description, &tapID), "tap", "creating the tap")

    micStreams = try inputLayout(mic).count

    let aggregate: [String: Any] = [
        kAudioAggregateDeviceNameKey: "Coulisses",
        kAudioAggregateDeviceUIDKey: "coulisses-\(UUID().uuidString)",
        kAudioAggregateDeviceMainSubDeviceKey: micUID,
        kAudioAggregateDeviceIsPrivateKey: true,
        kAudioAggregateDeviceIsStackedKey: false,
        // Started with the device, the tap would hold its I/O back until something plays.
        kAudioAggregateDeviceTapAutoStartKey: false,
        kAudioAggregateDeviceSubDeviceListKey: [[kAudioSubDeviceUIDKey: micUID]],
        kAudioAggregateDeviceTapListKey: [
            [
                kAudioSubTapDriftCompensationKey: true,
                kAudioSubTapUIDKey: description.uuid.uuidString,
            ]
        ],
    ]
    try check(
        AudioHardwareCreateAggregateDevice(aggregate as CFDictionary, &aggregateID), "aggregat",
        "creating the aggregate device")

    // The microphone's clock runs the aggregate: it is asked for the recording's rate.
    var nominal = rate
    var rateWhere = address(kAudioDevicePropertyNominalSampleRate)
    AudioObjectSetPropertyData(
        aggregateID, &rateWhere, 0, nil, UInt32(MemoryLayout<Float64>.size), &nominal)
    var actual: Float64 = 0
    var rateSize = UInt32(MemoryLayout<Float64>.size)
    try check(
        AudioObjectGetPropertyData(aggregateID, &rateWhere, 0, nil, &rateSize, &actual),
        "frequence", "reading the rate")
    if abs(actual - rate) > 0.5 {
        throw Failure(code: "frequence", detail: "\(actual) Hz")
    }
    actualRate = actual

    // The microphone's streams first, then the tap's (one channel).
    let layout = try inputLayout(aggregateID)
    // The microphone's streams first; the tap's last (one channel).
    guard layout.count >= micStreams + 1, layout.last == 1 else {
        throw Failure(code: "format", detail: "input layout \(layout)")
    }
    micChannels = Array(layout.prefix(micStreams))
    if micChannels.reduce(0, +) < wanted {
        throw Failure(code: "format", detail: "\(micChannels) channels, \(wanted) wanted")
    }
    guard try inputStreamsAreFloat(aggregateID) else {
        throw Failure(code: "format", detail: "not interleaved float32")
    }

    let width = wanted + 1
    try check(
        AudioDeviceCreateIOProcIDWithBlock(&procID, aggregateID, nil) {
            _, inputData, inputTime, _, _ in
            let buffers = UnsafeMutableAudioBufferListPointer(
                UnsafeMutablePointer(mutating: inputData))
            calls += 1
            guard buffers.count == layout.count else { return }
            let tap = buffers[buffers.count - 1]
            lastTapBytes = tap.mDataByteSize
            let frames = Int(tap.mDataByteSize) / MemoryLayout<Float32>.size
            if frames == 0 { return }
            // Sound the Mac could not deliver: said, never hidden (P8).
            let time = inputTime.pointee.mSampleTime
            var lost = 0
            if expected >= 0 && time - expected >= 1 {
                lost = Int(time - expected)
            }
            expected = time + Float64(frames)
            var interleaved = [Float32](repeating: 0, count: frames * width)
            // Frames a buffer did not hold are left at zero: counted as lost, never hidden.
            var missing = 0
            var column = 0
            for (index, channels) in micChannels.enumerated() where column < wanted {
                let available =
                    buffers[index].mData == nil
                    ? 0 : Int(buffers[index].mDataByteSize) / MemoryLayout<Float32>.size
                missing = max(missing, frames - available / max(channels, 1))
                guard let samples = buffers[index].mData?.assumingMemoryBound(to: Float32.self)
                else {
                    column += channels
                    continue
                }
                for channel in 0..<channels where column < wanted {
                    for frame in 0..<frames where frame * channels + channel < available {
                        interleaved[frame * width + column] = samples[frame * channels + channel]
                    }
                    column += 1
                }
            }
            if let samples = tap.mData?.assumingMemoryBound(to: Float32.self) {
                for frame in 0..<frames {
                    interleaved[frame * width + wanted] = samples[frame]
                }
            } else {
                missing = frames
            }
            lost += max(missing, 0)
            var data = Data(capacity: 8 + frames * width * 4)
            withUnsafeBytes(of: UInt32(frames).littleEndian) { data.append(contentsOf: $0) }
            withUnsafeBytes(of: UInt32(clamping: lost).littleEndian) { data.append(contentsOf: $0) }
            interleaved.withUnsafeBufferPointer { data.append($0) }
            let first = !announced
            announced = true
            writing.async {
                // Ready once sound flows (the aggregate takes a moment to start): the
                // recording starts with it, nothing said before is missing.
                if first {
                    say([
                        "event": "ready", "rate": actualRate, "channels": wanted,
                        "micro": micName, "micro_streams": micChannels,
                    ])
                }
                do {
                    try output.write(contentsOf: data)
                } catch {
                    // The service is gone: nothing left to record for.
                    tearDown()
                    exit(0)
                }
            }
        }, "demarrage", "creating the I/O procedure")
    try check(AudioDeviceStart(aggregateID, procID), "demarrage", "starting the device")
}

signal(SIGPIPE, SIG_IGN)
do {
    try start()
} catch let failure as Failure {
    tearDown()
    say(["event": "error", "code": failure.code, "detail": failure.detail])
    exit(1)
}

func finish() -> Never {
    tearDown()
    // What was heard before stopping is written, then the pipe is closed.
    writing.sync {}
    exit(0)
}

// Said while no sound flows yet, for the service's log (a permission being asked…).
let waiting = DispatchSource.makeTimerSource(queue: .main)
waiting.schedule(deadline: .now() + 2, repeating: 2)
waiting.setEventHandler {
    if announced {
        waiting.cancel()
    } else {
        say(["event": "waiting", "callbacks": calls, "tap_bytes": Int(lastTapBytes)])
    }
}
waiting.resume()

let terminate = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
signal(SIGTERM, SIG_IGN)
terminate.setEventHandler { finish() }
terminate.resume()

Thread.detachNewThread {
    // The standard input closes: the service asks it to stop, or is gone.
    while FileHandle.standardInput.availableData.count > 0 {}
    DispatchQueue.main.async { finish() }
}

dispatchMain()
