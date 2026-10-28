// Optional macOS check: swift scripts/check_label_qr.swift --count=9 page-1.png page-2.png
import AppKit
import Vision

var payloads: [String] = []
var paths = Array(CommandLine.arguments.dropFirst())
var count = 3
if let first = paths.first, first.hasPrefix("--count="), let value = Int(first.dropFirst(8)), value > 0 {
    count = value
    paths.removeFirst()
}
for path in paths {
    guard let image = NSImage(contentsOfFile: path),
          let bitmap = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        fatalError("Cannot open sample page: \(path)")
    }
    let request = VNDetectBarcodesRequest()
    request.symbologies = [.qr]
    try VNImageRequestHandler(cgImage: bitmap).perform([request])
    let found = (request.results ?? []).compactMap { $0.payloadStringValue }
    print("\(path): \(found)")
    payloads.append(contentsOf: found)
}
let expected = Set((1...count).map { "CRT20261000\($0)EU" })
guard Set(payloads) == expected, payloads.count == expected.count else {
    fatalError("Rendered QR codes did not decode to all \(count) expected carton IDs")
}
print("All sample QR codes decoded successfully using Apple Vision.")
