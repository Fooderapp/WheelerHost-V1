// swift-tools-version:5.7
import PackageDescription

let package = Package(
    name: "UserHIDGamepad",
    platforms: [.macOS(.v12)],
    products: [
        .executable(name: "UserHIDGamepad", targets: ["UserHIDGamepad"]) 
    ],
    targets: [
        .executableTarget(
            name: "UserHIDGamepad",
            path: "Sources",
            linkerSettings: [
                .linkedFramework("IOKit"),
                .linkedFramework("CoreFoundation")
            ]
        )
    ]
)
