// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "MacAudioHelper",
    platforms: [ .macOS(.v13) ],
    products: [ .executable(name: "MacAudioHelper", targets: ["MacAudioHelper"]) ],
    targets: [
        .executableTarget(name: "MacAudioHelper", path: "Sources")
    ]
)

