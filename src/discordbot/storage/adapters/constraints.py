"""Conservative CHECK and UNIQUE comparison against reviewed DDL.

SQLite column pragmas omit CHECK expressions. Lex stored CREATE TABLE text so
comments, literals and quoted identifiers cannot hide or invent a CHECK keyword.
Only token/group equality is approved; unknown expressions fail closed. Other
schema properties remain the responsibility of the existing metadata/DDL gates.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import NamedTuple


class Token(NamedTuple):
    kind: str
    value: str


type Expression = tuple[Token | Expression, ...]


def _fold(value: str) -> str:
    # SQLite identifier case folding is ASCII, not Unicode case folding.
    return value.translate(str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"))


def _tokens(sql: str) -> list[Token]:
    tokens: list[Token] = []
    index = 0
    while index < len(sql):
        char = sql[index]
        if char in " \t\r\n\f":
            index += 1
        elif sql.startswith("--", index):
            end = sql.find("\n", index + 2)
            index = len(sql) if end < 0 else end + 1
        elif sql.startswith("/*", index):
            end = sql.find("*/", index + 2)
            if end < 0:
                raise ValueError("unterminated SQL comment")
            index = end + 2
        elif char in "'\"`[":
            close = "]" if char == "[" else char
            index += 1
            value = []
            while index < len(sql):
                if sql[index] == close:
                    if char != "[" and sql[index:index + 2] == close * 2:
                        value.append(close)
                        index += 2
                        continue
                    index += 1
                    break
                value.append(sql[index])
                index += 1
            else:
                raise ValueError("unterminated SQL quote")
            # Do not fold string literals or equate double-quoted strings with
            # single-quoted literals. Only known identifiers may match the DDL.
            tokens.append(Token("string" if char == "'" else "identifier", "".join(value)))
        elif char.isalpha() or char == "_" or ord(char) >= 128:
            start = index
            index += 1
            while index < len(sql) and (sql[index].isalnum() or sql[index] in "_$" or ord(sql[index]) >= 128):
                index += 1
            tokens.append(Token("word", _fold(sql[start:index])))
        else:
            if char == "\x00":
                raise ValueError("NUL in SQL")
            tokens.append(Token("symbol", char))
            index += 1
    return tokens


def check_expressions(sql: str) -> tuple[Expression, ...]:
    """Extract column/table CHECKs, keeping literals, operators and group order.

    Whitespace/comments, ASCII identifier case, identifier quoting and redundant
    singleton parentheses are harmless. No algebra, operator substitutions or
    truth-value evaluation is used to authorize an unreviewed expression.
    """
    tokens = _tokens(sql)
    checks = []
    index = 0
    while index < len(tokens):
        if tokens[index] != Token("word", "check"):
            index += 1
            continue
        index += 1
        if index == len(tokens) or tokens[index] != Token("symbol", "("):
            raise ValueError("CHECK has no expression")
        groups: list[list[Token | Expression]] = [[]]
        index += 1
        while index < len(tokens):
            token = tokens[index]
            index += 1
            if token == Token("symbol", "("):
                groups.append([])
            elif token == Token("symbol", ")"):
                group = groups.pop()
                if not group:
                    raise ValueError("empty CHECK group")
                if not groups:
                    # Peel wrappers around the entire expression as well.
                    expression = tuple(group)
                    while len(expression) == 1 and not isinstance(expression[0], Token):
                        expression = expression[0]
                    checks.append(expression)
                    break
                groups[-1].append(group[0] if len(group) == 1 else tuple(group))
            else:
                groups[-1].append(Token("word", _fold(token.value)) if token.kind == "identifier" else token)
        else:
            raise ValueError("unterminated CHECK expression")
    return tuple(checks)


def checks_match(conn: sqlite3.Connection, table: str, reviewed_ddl: str) -> bool:
    """Compare live constraints only to caller-supplied, reviewed definitions."""
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    if row is None or not isinstance(row[0], str):
        return False
    expected = check_expressions(reviewed_ddl)
    try:
        return check_expressions(row[0]) == expected
    except ValueError:
        return False


type UniqueKey = tuple[str | None, int, str]
type UniqueIndex = tuple[str, int, tuple[UniqueKey, ...]]


def _unique_indexes(conn: sqlite3.Connection, table: str) -> tuple[UniqueIndex, ...]:
    """Names are not identity; compare SQLite's effective unique key metadata.

    Parameterized pragma functions keep even hostile index names out of SQL.
    Include origin, partial flag, key order/direction and collation. Explicit
    unique indexes and expression keys cannot masquerade as reviewed autoindexes.
    Nonunique query indexes do not constrain writes and remain allowed.
    """
    result: list[UniqueIndex] = []
    for _, name, unique, origin, partial in conn.execute(
        "SELECT * FROM pragma_index_list(?)", (table,),
    ):
        if unique:
            keys = tuple(
                (None if column is None else _fold(column), descending, _fold(collation))
                for _, _, column, descending, collation, key in conn.execute(
                    "SELECT * FROM pragma_index_xinfo(?)", (name,),
                ) if key
            )
            result.append((origin, partial, keys))
    return tuple(sorted(result, key=repr))


def uniques_match(conn: sqlite3.Connection, table: str, reviewed_ddl: str) -> bool:
    """Compare against reviewed DDL in a disposable, empty in-memory database.

    Never execute source DDL here. SQLite resolves supported quoting/constraint
    placement itself; names of constraints and autoindexes are immaterial.
    """
    with closing(sqlite3.connect(":memory:")) as reference:
        reference.execute(reviewed_ddl)
        return _unique_indexes(conn, table) == _unique_indexes(reference, table)
