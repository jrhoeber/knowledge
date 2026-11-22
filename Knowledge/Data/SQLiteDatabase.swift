import Foundation
import SQLite3

/// A value bound to a SQL statement parameter.
nonisolated enum SQLiteValue: Sendable, Equatable {
    case integer(Int64)
    case real(Double)
    case text(String)
    case null

    static func int(_ value: Int) -> SQLiteValue { .integer(Int64(value)) }
    static func bool(_ value: Bool) -> SQLiteValue { .integer(value ? 1 : 0) }
}

nonisolated enum SQLiteError: Error, CustomStringConvertible {
    case open(path: String, message: String)
    case prepare(message: String, sql: String)
    case bind(message: String, sql: String)
    case step(message: String, sql: String)
    case execute(message: String, sql: String)

    var description: String {
        switch self {
        case let .open(path, message): "Could not open database at \(path): \(message)"
        case let .prepare(message, sql): "Could not prepare \"\(sql)\": \(message)"
        case let .bind(message, sql): "Could not bind parameters for \"\(sql)\": \(message)"
        case let .step(message, sql): "Could not run \"\(sql)\": \(message)"
        case let .execute(message, sql): "Could not execute \"\(sql)\": \(message)"
        }
    }
}

nonisolated(unsafe) private let transientDestructor = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

/// A minimal wrapper over the SQLite C API. The app's data volume is small enough
/// that statements are prepared per call; no external dependency is needed.
nonisolated final class SQLiteDatabase {
    private let handle: OpaquePointer

    /// Opens a database file. Pass `":memory:"` for a private in-memory database.
    init(path: String, readOnly: Bool) throws {
        var connection: OpaquePointer?
        let flags = readOnly ? SQLITE_OPEN_READONLY : (SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
        let status = sqlite3_open_v2(path, &connection, flags, nil)
        guard status == SQLITE_OK, let connection else {
            let message = connection.map { String(cString: sqlite3_errmsg($0)) } ?? "status \(status)"
            if let connection { sqlite3_close_v2(connection) }
            throw SQLiteError.open(path: path, message: message)
        }
        handle = connection
    }

    deinit {
        sqlite3_close_v2(handle)
    }

    /// Runs one or more statements that take no parameters and return no rows.
    func execute(_ sql: String) throws {
        var errorPointer: UnsafeMutablePointer<CChar>?
        guard sqlite3_exec(handle, sql, nil, nil, &errorPointer) == SQLITE_OK else {
            let message = errorPointer.map { String(cString: $0) } ?? lastErrorMessage
            sqlite3_free(errorPointer)
            throw SQLiteError.execute(message: message, sql: sql)
        }
    }

    /// Runs a single statement, ignoring any rows it returns.
    func run(_ sql: String, _ arguments: [SQLiteValue] = []) throws {
        let statement = try prepare(sql, arguments)
        defer { sqlite3_finalize(statement) }
        let status = sqlite3_step(statement)
        guard status == SQLITE_DONE || status == SQLITE_ROW else {
            throw SQLiteError.step(message: lastErrorMessage, sql: sql)
        }
    }

    /// Runs a query and maps every returned row.
    func query<T>(_ sql: String, _ arguments: [SQLiteValue] = [], map: (SQLiteRow) throws -> T) throws -> [T] {
        let statement = try prepare(sql, arguments)
        defer { sqlite3_finalize(statement) }
        var results: [T] = []
        while true {
            let status = sqlite3_step(statement)
            if status == SQLITE_ROW {
                results.append(try map(SQLiteRow(statement: statement)))
            } else if status == SQLITE_DONE {
                return results
            } else {
                throw SQLiteError.step(message: lastErrorMessage, sql: sql)
            }
        }
    }

    /// Runs a query and maps the first row, if any.
    func queryFirst<T>(_ sql: String, _ arguments: [SQLiteValue] = [], map: (SQLiteRow) throws -> T) throws -> T? {
        try query(sql, arguments, map: map).first
    }

    /// Returns the integer in the first column of the first row, or `nil` when there is no row or it is NULL.
    func scalarInt(_ sql: String, _ arguments: [SQLiteValue] = []) throws -> Int? {
        try queryFirst(sql, arguments) { $0.isNull(0) ? nil : $0.int(0) } ?? nil
    }

    func transaction(_ body: () throws -> Void) throws {
        try execute("BEGIN IMMEDIATE")
        do {
            try body()
            try execute("COMMIT")
        } catch {
            try? execute("ROLLBACK")
            throw error
        }
    }

    var userVersion: Int {
        get { (try? scalarInt("PRAGMA user_version")) ?? 0 }
    }

    func setUserVersion(_ version: Int) throws {
        try execute("PRAGMA user_version = \(version)")
    }

    private func prepare(_ sql: String, _ arguments: [SQLiteValue]) throws -> OpaquePointer {
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(handle, sql, -1, &statement, nil) == SQLITE_OK, let statement else {
            throw SQLiteError.prepare(message: lastErrorMessage, sql: sql)
        }
        for (index, value) in arguments.enumerated() {
            let position = Int32(index + 1)
            let status: Int32 = switch value {
            case .integer(let number): sqlite3_bind_int64(statement, position, number)
            case .real(let number): sqlite3_bind_double(statement, position, number)
            case .text(let string): sqlite3_bind_text(statement, position, string, -1, transientDestructor)
            case .null: sqlite3_bind_null(statement, position)
            }
            guard status == SQLITE_OK else {
                sqlite3_finalize(statement)
                throw SQLiteError.bind(message: lastErrorMessage, sql: sql)
            }
        }
        return statement
    }

    private var lastErrorMessage: String {
        String(cString: sqlite3_errmsg(handle))
    }
}

/// Read access to the current row of a running query. Only valid inside the `map` closure.
nonisolated struct SQLiteRow {
    fileprivate let statement: OpaquePointer

    func int(_ column: Int32) -> Int {
        Int(sqlite3_column_int64(statement, column))
    }

    func double(_ column: Int32) -> Double {
        sqlite3_column_double(statement, column)
    }

    func bool(_ column: Int32) -> Bool {
        sqlite3_column_int64(statement, column) != 0
    }

    func string(_ column: Int32) -> String {
        guard let text = sqlite3_column_text(statement, column) else { return "" }
        return String(cString: text)
    }

    func optionalString(_ column: Int32) -> String? {
        isNull(column) ? nil : string(column)
    }

    func isNull(_ column: Int32) -> Bool {
        sqlite3_column_type(statement, column) == SQLITE_NULL
    }
}
