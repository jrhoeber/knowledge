# Build and run Knowledge in the iOS Simulator.
#
#   make build                 build the app (Debug, simulator)
#   make clean                 delete build products and uninstall the app from the
#                              simulator (wiping its data), then build from scratch
#   make run                   build, then install and launch in the simulator
#   make run ARGS="-resetState -topics mental_math,vocabulary -seed 3"
#   make run SIM="iPhone 17 Pro Max"

PROJECT   := Knowledge.xcodeproj
SCHEME    := Knowledge
BUNDLE_ID := com.jordanhoeber.knowledge
SIM       ?= iPhone 17 Pro
ARGS      ?=

DERIVED   := build/DerivedData
APP       := $(DERIVED)/Build/Products/Debug-iphonesimulator/Knowledge.app

# Several runtimes can each have a device with the same name. Prefer one that is
# already booted, otherwise the newest runtime (simctl lists runtimes oldest first).
# ( is spelled $(LPAREN) because make would count a bare one inside $(shell ...).
LPAREN := (
SIM_ID := $(shell xcrun simctl list devices available \
	| grep -F "    $(SIM) $(LPAREN)" \
	| awk '/\(Booted\)/ { booted = $$0 } { last = $$0 } END { print (booted ? booted : last) }' \
	| grep -oE '[0-9A-F]{8}-([0-9A-F]{4}-){3}[0-9A-F]{12}')

XCODEBUILD := xcodebuild -project $(PROJECT) -scheme $(SCHEME) -configuration Debug \
	-destination 'platform=iOS Simulator,id=$(SIM_ID)' -derivedDataPath $(DERIVED)

.DEFAULT_GOAL := build
.PHONY: build clean run check-sim

check-sim:
	@test -n "$(SIM_ID)" || { echo "No available simulator named '$(SIM)'. See: xcrun simctl list devices available"; exit 1; }

build: check-sim
	$(XCODEBUILD) build

clean: check-sim
	$(XCODEBUILD) clean
	rm -rf $(DERIVED)
	@# Uninstalling (which also deletes the app's data) needs a booted device.
	xcrun simctl bootstatus $(SIM_ID) -b
	xcrun simctl uninstall $(SIM_ID) $(BUNDLE_ID)
	$(MAKE) build

run: build
	xcrun simctl bootstatus $(SIM_ID) -b
	@# Xcode 27 shows simulators in DeviceHub; earlier versions ship Simulator.app.
	open -b com.apple.dt.Devices 2>/dev/null || open -b com.apple.iphonesimulator
	xcrun simctl install $(SIM_ID) $(APP)
	xcrun simctl launch --terminate-running-process $(SIM_ID) $(BUNDLE_ID) $(ARGS)
