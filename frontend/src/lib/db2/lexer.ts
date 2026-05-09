import { DB2_KEYWORDS } from "@src/lib/db2/language";
import type { Db2Token } from "@src/types/db2";

const KEYWORDS: ReadonlySet<string> = new Set(DB2_KEYWORDS);

export function tokenizeDb2Program(source: string): Db2Token[] {
  const tokens: Db2Token[] = [];
  let index = 0;
  let line = 1;
  let column = 1;

  const isAtEnd = (offset = 0) => index + offset >= source.length;
  const peek = (offset = 0) => source[index + offset] ?? "";

  const advance = () => {
    const character = source[index] ?? "";
    index += 1;
    column += 1;
    return character;
  };

  const advanceLine = () => {
    index += 1;
    line += 1;
    column = 1;
  };

  const pushToken = (kind: Db2Token["kind"], lexeme: string, value = lexeme, tokenLine = line, tokenColumn = column) => {
    tokens.push({ kind, lexeme, value, line: tokenLine, column: tokenColumn });
  };

  const readWhile = (predicate: (character: string) => boolean) => {
    let value = "";
    while (!isAtEnd() && predicate(peek())) {
      value += advance();
    }
    return value;
  };

  const readIdentifier = () => {
    const startColumn = column;
    let value = advance();
    value += readWhile((character) => /[a-zA-Z0-9_]/.test(character));
    const upperValue = value.toUpperCase();
    pushToken(KEYWORDS.has(upperValue) ? "Keyword" : "Id", value, value, line, startColumn);
  };

  const readNumber = () => {
    const startColumn = column;
    let value = "";

    if (peek() === "-") {
      value += advance();
    }

    value += readWhile((character) => /[0-9]/.test(character));

    if (!isAtEnd() && peek() === "." && /[0-9]/.test(peek(1))) {
      value += advance();
      value += readWhile((character) => /[0-9]/.test(character));
    }

    pushToken("Number", value, value, line, startColumn);
  };

  const readString = () => {
    const quote = advance();
    const startColumn = column - 1;
    let value = "";

    while (!isAtEnd() && peek() !== quote) {
      if (peek() === "\\" && !isAtEnd(1)) {
        value += advance();
      }

      value += advance();
    }

    if (isAtEnd()) {
      pushToken("ERROR", value, `Unterminated string literal`, line, startColumn);
      return;
    }

    advance();
    pushToken("String", `${quote}${value}${quote}`, value, line, startColumn);
  };

  while (!isAtEnd()) {
    const character = peek();

    if (character === " " || character === "\t" || character === "\r") {
      advance();
      continue;
    }

    if (character === "\n") {
      advanceLine();
      continue;
    }

    if (character === "-" && peek(1) === "-") {
      readWhile((current) => current !== "\n");
      continue;
    }

    if (/[a-zA-Z_]/.test(character)) {
      readIdentifier();
      continue;
    }

    if (character === "-" && /[0-9]/.test(peek(1))) {
      readNumber();
      continue;
    }

    if (/[0-9]/.test(character)) {
      readNumber();
      continue;
    }

    if (character === '"' || character === "'") {
      readString();
      continue;
    }

    const twoCharacterOperator = `${character}${peek(1)}`;
    if (["<=", ">=", "!="].includes(twoCharacterOperator)) {
      const startColumn = column;
      advance();
      advance();
      pushToken("Operator", twoCharacterOperator, twoCharacterOperator, line, startColumn);
      continue;
    }

    if (["=", "<", ">"].includes(character)) {
      const startColumn = column;
      advance();
      pushToken("Operator", character, character, line, startColumn);
      continue;
    }

    if (["*", ",", "(", ")", ";", "."].includes(character)) {
      const startColumn = column;
      advance();
      pushToken("Symbol", character, character, line, startColumn);
      continue;
    }

    const startColumn = column;
    advance();
    pushToken("ERROR", character, `Unexpected character ${character}`, line, startColumn);
  }

  tokens.push({ kind: "EOF", lexeme: "EOF", value: "EOF", line, column });
  return tokens;
}