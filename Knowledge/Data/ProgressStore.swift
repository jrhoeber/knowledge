import Foundation

/// Spaced-repetition state for one content item the user has seen.
nonisolated struct ItemState: Equatable, Sendable {
    let topic: Topic
    let itemID: Int
    var difficulty: Int
    var box: Int
    var dueSequence: Int
    var dueAt: Date
    var seenCount: Int
    var correctCount: Int
    var lastSequence: Int
}

/// One answered question, as used by the proficiency model.
nonisolated struct AnswerRecord: Equatable, Sendable {
    let difficulty: Int
    let isCorrect: Bool
}

nonisolated struct DifficultyTally: Equatable, Sendable {
    var answered = 0
    var correct = 0

    var accuracy: Double? { answered == 0 ? nil : Double(correct) / Double(answered) }
}

nonisolated struct TopicTally: Equatable, Sendable {
    var answered = 0
    var correct = 0
    /// Index 0 is difficulty 1.
    var byDifficulty = Array(repeating: DifficultyTally(), count: 5)

    var accuracy: Double? { answered == 0 ? nil : Double(correct) / Double(answered) }
}

/// The user's answer history and review schedule, stored in a writable SQLite file
/// in Application Support. Nothing leaves the device.
final class ProgressStore {
    private static let schemaVersion = 1
    private let database: SQLiteDatabase

    /// - Parameter url: Database file location, or `nil` for an in-memory store (tests, previews).
    init(url: URL?) throws {
        if let url {
            try FileManager.default.createDirectory(
                at: url.deletingLastPathComponent(), withIntermediateDirectories: true
            )
        }
        database = try SQLiteDatabase(path: url?.path ?? ":memory:", readOnly: false)
        try database.execute("PRAGMA journal_mode = WAL")
        try migrate()
    }

    static func defaultURL() throws -> URL {
        let support = try FileManager.default.url(
            for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true
        )
        return support.appending(path: "Progress", directoryHint: .isDirectory)
            .appending(path: "progress.sqlite")
    }

    /// Deletes the database file and its WAL companions.
    static func deleteStore(at url: URL) {
        for suffix in ["", "-wal", "-shm"] {
            try? FileManager.default.removeItem(at: URL(filePath: url.path + suffix))
        }
    }

    private func migrate() throws {
        guard database.userVersion < Self.schemaVersion else { return }
        try database.execute("""
            CREATE TABLE IF NOT EXISTS answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seq INTEGER NOT NULL,
                topic TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                difficulty INTEGER NOT NULL,
                correct INTEGER NOT NULL,
                answered_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS answers_by_topic ON answers(topic, seq);
            CREATE TABLE IF NOT EXISTS items (
                topic TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                difficulty INTEGER NOT NULL,
                box INTEGER NOT NULL,
                due_seq INTEGER NOT NULL,
                due_at REAL NOT NULL,
                seen_count INTEGER NOT NULL,
                correct_count INTEGER NOT NULL,
                last_seq INTEGER NOT NULL,
                PRIMARY KEY (topic, item_id)
            ) WITHOUT ROWID;
            CREATE INDEX IF NOT EXISTS items_by_due ON items(topic, due_seq);
            CREATE INDEX IF NOT EXISTS items_by_recency ON items(topic, difficulty, last_seq);
            """)
        try database.setUserVersion(Self.schemaVersion)
    }

    // MARK: Reads

    /// The sequence number the next answer will receive. Sequence numbers count every
    /// answer across all topics and drive in-session review spacing.
    func nextSequence() throws -> Int {
        (try database.scalarInt("SELECT MAX(seq) FROM answers") ?? 0) + 1
    }

    func state(topic: Topic, itemID: Int) throws -> ItemState? {
        try database.queryFirst(
            "\(Self.itemColumns) WHERE topic = ? AND item_id = ?",
            [.text(topic.rawValue), .int(itemID)],
            map: Self.itemState
        )
    }

    /// Items whose review is due, most urgent (lowest box, then most overdue) first.
    /// Items at `difficulty` that are due for review, most urgent first.
    func dueItems(topic: Topic, difficulty: Int, sequence: Int, now: Date, limit: Int) throws -> [ItemState] {
        try database.query(
            """
            \(Self.itemColumns) WHERE topic = ? AND difficulty = ? AND due_seq <= ? AND due_at <= ?
            ORDER BY box ASC, due_seq ASC LIMIT ?
            """,
            [.text(topic.rawValue), .int(difficulty), .int(sequence), .real(now.timeIntervalSince1970), .int(limit)],
            map: Self.itemState
        )
    }

    func seenItemIDs(topic: Topic) throws -> Set<Int> {
        Set(try database.query("SELECT item_id FROM items WHERE topic = ?", [.text(topic.rawValue)]) { $0.int(0) })
    }

    /// The seen item at `difficulty` that was shown longest ago, used when every item
    /// at that level has been seen.
    func leastRecentlySeenItem(topic: Topic, difficulty: Int, excluding excluded: Int?) throws -> Int? {
        try database.scalarInt(
            "SELECT item_id FROM items WHERE topic = ? AND difficulty = ? AND item_id != ? ORDER BY last_seq ASC LIMIT 1",
            [.text(topic.rawValue), .int(difficulty), .int(excluded ?? -1)]
        )
    }

    /// The most recent answers in a topic, newest first.
    func recentAnswers(topic: Topic, limit: Int) throws -> [AnswerRecord] {
        try database.query(
            "SELECT difficulty, correct FROM answers WHERE topic = ? ORDER BY seq DESC LIMIT ?",
            [.text(topic.rawValue), .int(limit)]
        ) { AnswerRecord(difficulty: $0.int(0), isCorrect: $0.bool(1)) }
    }

    func answerCount(topic: Topic) throws -> Int {
        try database.scalarInt("SELECT COUNT(*) FROM answers WHERE topic = ?", [.text(topic.rawValue)]) ?? 0
    }

    func tally(topic: Topic) throws -> TopicTally {
        var tally = TopicTally()
        let rows = try database.query(
            "SELECT difficulty, COUNT(*), SUM(correct) FROM answers WHERE topic = ? GROUP BY difficulty",
            [.text(topic.rawValue)]
        ) { (difficulty: $0.int(0), answered: $0.int(1), correct: $0.int(2)) }
        for row in rows where (1...5).contains(row.difficulty) {
            tally.byDifficulty[row.difficulty - 1] = DifficultyTally(answered: row.answered, correct: row.correct)
            tally.answered += row.answered
            tally.correct += row.correct
        }
        return tally
    }

    // MARK: Writes

    /// Appends an answer to the history and stores the item's new review schedule.
    func record(
        topic: Topic, itemID: Int, difficulty: Int, isCorrect: Bool,
        sequence: Int, now: Date, schedule: ReviewSchedule
    ) throws {
        let previous = try state(topic: topic, itemID: itemID)
        try database.transaction {
            try database.run(
                "INSERT INTO answers (seq, topic, item_id, difficulty, correct, answered_at) VALUES (?, ?, ?, ?, ?, ?)",
                [.int(sequence), .text(topic.rawValue), .int(itemID), .int(difficulty), .bool(isCorrect),
                 .real(now.timeIntervalSince1970)]
            )
            try database.run(
                """
                INSERT OR REPLACE INTO items
                    (topic, item_id, difficulty, box, due_seq, due_at, seen_count, correct_count, last_seq)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [.text(topic.rawValue), .int(itemID), .int(difficulty), .int(schedule.box),
                 .int(schedule.dueSequence), .real(schedule.dueAt.timeIntervalSince1970),
                 .int((previous?.seenCount ?? 0) + 1),
                 .int((previous?.correctCount ?? 0) + (isCorrect ? 1 : 0)),
                 .int(sequence)]
            )
        }
    }

    /// Erases the whole answer history and every review schedule.
    func deleteAll() throws {
        try database.transaction {
            try database.execute("DELETE FROM answers; DELETE FROM items;")
        }
    }

    // MARK: Row mapping

    private static let itemColumns = """
        SELECT topic, item_id, difficulty, box, due_seq, due_at, seen_count, correct_count, last_seq FROM items
        """

    private static func itemState(_ row: SQLiteRow) -> ItemState {
        ItemState(
            topic: Topic(rawValue: row.string(0)) ?? .mentalMath,
            itemID: row.int(1),
            difficulty: row.int(2),
            box: row.int(3),
            dueSequence: row.int(4),
            dueAt: Date(timeIntervalSince1970: row.double(5)),
            seenCount: row.int(6),
            correctCount: row.int(7),
            lastSequence: row.int(8)
        )
    }
}
