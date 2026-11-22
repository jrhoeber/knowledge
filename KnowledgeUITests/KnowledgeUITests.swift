import XCTest

/// Walks through the app as a user would. Screenshots are attached to the test
/// results (`xcrun xcresulttool export attachments`) for visual review.
final class KnowledgeUITests: XCTestCase {
    override func setUp() {
        continueAfterFailure = false
    }

    @MainActor
    func testFirstRunOnboardingQuizTopicsAndProfile() throws {
        let app = XCUIApplication()
        app.launchArguments = ["-resetState", "-seed", "7", "-disableAnimations"]
        app.launch()

        // Onboarding: nothing selected, so Start is disabled.
        let start = app.buttons["startButton"]
        XCTAssertTrue(start.waitForExistence(timeout: 10))
        XCTAssertFalse(start.isEnabled)
        attachScreenshot(app, named: "01-onboarding")

        app.buttons["topicCard.mental_math"].tap()
        app.buttons["topicCard.vocabulary"].tap()
        XCTAssertTrue(start.isEnabled)
        attachScreenshot(app, named: "02-onboarding-selected")
        start.tap()

        // Straight into questions.
        XCTAssertTrue(prompt(in: app).waitForExistence(timeout: 10))
        attachScreenshot(app, named: "03-first-question")
        answerQuestions(24, in: app, screenshotsFor: [0, 1, 2, 3])

        // Menu → Profile.
        openMenuItem("menu.profile", in: app)
        XCTAssertTrue(app.navigationBars["Profile"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.descendants(matching: .any)["proficiencyCard.mental_math"].exists)
        XCTAssertTrue(app.descendants(matching: .any)["proficiencyCard.vocabulary"].exists)
        attachScreenshot(app, named: "06-profile")
        app.swipeUp()
        attachScreenshot(app, named: "07-profile-scrolled")
        app.navigationBars.buttons.element(boundBy: 0).tap()

        // Profile → Reset Progress → confirm: every topic starts over.
        openMenuItem("menu.profile", in: app)
        let reset = app.buttons["resetProgressButton"]
        XCTAssertTrue(reset.waitForExistence(timeout: 5))
        let cards = ["mental_math", "vocabulary"].map { app.descendants(matching: .any)["proficiencyCard.\($0)"] }
        for card in cards { XCTAssertFalse(card.label.contains(", 0 answers"), card.label) }
        app.swipeUp()
        reset.tap()
        // iOS 26 reports the dialog's button twice in the accessibility tree.
        let confirm = app.buttons["confirmResetProgress"].firstMatch
        XCTAssertTrue(confirm.waitForExistence(timeout: 5))
        attachScreenshot(app, named: "07b-reset-confirmation")
        confirm.tap()
        XCTAssertTrue(confirm.waitForNonExistence(timeout: 5))
        for card in cards { XCTAssertTrue(card.label.contains(", 0 answers"), card.label) }
        XCTAssertFalse(reset.isEnabled)
        attachScreenshot(app, named: "07c-profile-after-reset")
        app.navigationBars.buttons.element(boundBy: 0).tap()
        answerQuestions(2, in: app)

        // Menu → Topics: turn Vocabulary off; Mental Math must then stay on.
        openMenuItem("menu.topics", in: app)
        XCTAssertTrue(app.navigationBars["Topics"].waitForExistence(timeout: 5))
        attachScreenshot(app, named: "08-topics")
        let vocabulary = app.switches["topicToggle.vocabulary"]
        XCTAssertEqual(vocabulary.value as? String, "1")
        vocabulary.switches.firstMatch.tap()
        XCTAssertEqual(vocabulary.value as? String, "0")
        XCTAssertFalse(app.switches["topicToggle.mental_math"].isEnabled)
        attachScreenshot(app, named: "09-topics-vocabulary-off")
        app.navigationBars.buttons.element(boundBy: 0).tap()

        // Only Mental Math questions now.
        for _ in 0..<4 {
            XCTAssertTrue(prompt(in: app).waitForExistence(timeout: 5))
            XCTAssertTrue(app.staticTexts["Mental Math"].exists)
            XCTAssertFalse(app.staticTexts["Vocabulary"].exists)
            answerQuestions(1, in: app)
        }

        // Relaunching skips onboarding and keeps settings.
        app.terminate()
        app.launchArguments = ["-disableAnimations"]
        app.launch()
        XCTAssertTrue(prompt(in: app).waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons["startButton"].exists)
        XCTAssertTrue(app.staticTexts["Mental Math"].exists)
    }

    @MainActor
    func testVocabularyFeedbackShowsAllMeanings() throws {
        let app = XCUIApplication()
        app.launchArguments = ["-resetState", "-topics", "vocabulary", "-seed", "12", "-disableAnimations"]
        app.launch()
        XCTAssertTrue(prompt(in: app).waitForExistence(timeout: 10))
        attachScreenshot(app, named: "10-vocabulary-question")
        app.buttons["option-0"].tap()
        XCTAssertTrue(app.buttons["continueButton"].waitForExistence(timeout: 5))
        XCTAssertTrue(meaningsCardScrollsIntoView(in: app), "Meanings card was not scrolled into view")
        attachScreenshot(app, named: "11-vocabulary-feedback")
        app.swipeUp()
        attachScreenshot(app, named: "12-vocabulary-meanings")

        // A word with several meanings: the start of the list must still come into view.
        let manyMeanings = NSPredicate(format: "label MATCHES '([3-9]|[1-9][0-9]) meanings'")
        var sawLongCard = false
        for _ in 0..<20 {
            app.buttons["continueButton"].tap()
            XCTAssertTrue(app.buttons["option-0"].waitForExistence(timeout: 5))
            app.buttons["option-0"].tap()
            XCTAssertTrue(app.buttons["continueButton"].waitForExistence(timeout: 5))
            if app.staticTexts.matching(manyMeanings).firstMatch.waitForExistence(timeout: 1) {
                XCTAssertTrue(meaningsCardScrollsIntoView(in: app), "Long meanings card was not scrolled into view")
                attachScreenshot(app, named: "13-vocabulary-many-meanings")
                sawLongCard = true
                break
            }
        }
        XCTAssertTrue(sawLongCard, "No word with three or more meanings in 20 questions")
    }

    // MARK: Helpers

    @MainActor
    private func prompt(in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any)["questionPrompt"]
    }

    @MainActor
    private func answerQuestions(_ count: Int, in app: XCUIApplication, screenshotsFor: Set<Int> = []) {
        for index in 0..<count {
            let option = app.buttons["option-\(index % 4)"]
            XCTAssertTrue(option.waitForExistence(timeout: 5))
            option.tap()
            let continueButton = app.buttons["continueButton"]
            XCTAssertTrue(continueButton.waitForExistence(timeout: 5))
            XCTAssertTrue(app.staticTexts["feedbackTitle"].exists)
            if screenshotsFor.contains(index) {
                attachScreenshot(app, named: "04-feedback-\(index)")
            }
            continueButton.tap()
            if screenshotsFor.contains(index) {
                _ = prompt(in: app).waitForExistence(timeout: 5)
                attachScreenshot(app, named: "05-question-\(index + 1)")
            }
        }
    }

    /// Waits for the post-answer auto-scroll: true once the top of the meanings card
    /// (at least 100 pt of it, or all of a shorter card) is visible above the feedback bar.
    @MainActor
    private func meaningsCardScrollsIntoView(in app: XCUIApplication) -> Bool {
        let card = app.descendants(matching: .any)["meaningsCard"]
        let feedbackTitle = app.staticTexts["feedbackTitle"]
        guard card.waitForExistence(timeout: 5) else { return false }
        let deadline = Date().addingTimeInterval(3)
        while Date() < deadline {
            let topEdgeVisible = card.frame.minY >= app.navigationBars.firstMatch.frame.maxY - 1
            let visibleHeight = feedbackTitle.frame.minY - card.frame.minY
            if topEdgeVisible, visibleHeight >= min(card.frame.height, 100) { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.1))
        }
        return false
    }

    @MainActor
    private func openMenuItem(_ identifier: String, in app: XCUIApplication) {
        let menu = app.buttons["menuButton"]
        XCTAssertTrue(menu.waitForExistence(timeout: 5))
        menu.tap()
        let item = app.buttons[identifier]
        XCTAssertTrue(item.waitForExistence(timeout: 5))
        item.tap()
    }

    @MainActor
    private func attachScreenshot(_ app: XCUIApplication, named name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
