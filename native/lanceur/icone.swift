// Draws the app's icon into an .iconset folder (then `iconutil` makes the .icns): the
// sound bars of the interface's mark (Lucide « audio-lines »), on the brick of the art
// direction, in the rounded square of macOS icons.
//
// Usage: swift icone.swift <dossier.iconset>

import AppKit

let target = URL(fileURLWithPath: CommandLine.arguments[1])
try FileManager.default.createDirectory(at: target, withIntermediateDirectories: true)

let brick = NSColor(red: 0xa6 / 255, green: 0x3d / 255, blue: 0x1e / 255, alpha: 1)

/// The bars of « audio-lines », on its 24-unit grid: (x, top, bottom).
let bars: [(CGFloat, CGFloat, CGFloat)] = [
    (2, 10, 13), (6, 6, 17), (10, 3, 21), (14, 8, 15), (18, 5, 18), (22, 10, 13),
]

func draw(size: Int) -> Data {
    let pixels = CGFloat(size)
    let rep = NSBitmapImageRep(
        bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size, bitsPerSample: 8,
        samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
        bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    // The macOS grid: the shape fills 824 of 1024, corners of 185.
    let inset = pixels * 100 / 1024
    let shape = NSRect(x: inset, y: inset, width: pixels - 2 * inset, height: pixels - 2 * inset)
    let tile = NSBezierPath(roundedRect: shape, xRadius: pixels * 185 / 1024, yRadius: pixels * 185 / 1024)
    brick.setFill()  // flat: no gradient (art direction)
    tile.fill()

    // The bars, centred, about half the tile wide.
    let unit = shape.width * 0.52 / 24
    let originX = shape.midX - 12 * unit
    let originY = shape.midY + 12 * unit
    NSColor.white.setStroke()
    for (x, top, bottom) in bars {
        let line = NSBezierPath()
        line.move(to: NSPoint(x: originX + x * unit, y: originY - top * unit))
        line.line(to: NSPoint(x: originX + x * unit, y: originY - bottom * unit))
        line.lineWidth = 2 * unit
        line.lineCapStyle = .round
        line.stroke()
    }
    NSGraphicsContext.restoreGraphicsState()
    return rep.representation(using: .png, properties: [:])!
}

for base in [16, 32, 128, 256, 512] {
    for scale in [1, 2] {
        let name = scale == 1 ? "icon_\(base)x\(base).png" : "icon_\(base)x\(base)@2x.png"
        try draw(size: base * scale).write(to: target.appendingPathComponent(name))
    }
}
