import { DB2_DATA_TYPES, DB2_INDEX_TYPES } from "@src/lib/db2/language";
import { tokenizeDb2Program } from "@src/lib/db2/lexer";
import type {
  Db2ComparisonOperator,
  Db2ParseContext,
  Db2ParseError,
  Db2ParseResult,
  Db2Program,
  Db2Scalar,
  Db2Statement,
  Db2Token,
  Db2WhereCondition,
} from "@src/types/db2";

const DATA_TYPES: ReadonlySet<string> = new Set(DB2_DATA_TYPES);
const INDEX_TYPES: ReadonlySet<string> = new Set(DB2_INDEX_TYPES);

class Db2ParserError extends Error {
  constructor(
    message: string,
    readonly context: Db2ParseContext,
  ) {
    super(message);
  }

  toParseError(): Db2ParseError {
    return {
      error: true,
      type: "SyntaxError",
      message: this.message,
      context: this.context,
    };
  }
}

class Db2Parser {
  private readonly tokens: Db2Token[];

  private current = 0;

  constructor(tokens: Db2Token[]) {
    this.tokens = tokens;
  }

  parseProgram(): Db2Program {
    const statements: Db2Statement[] = [];
    const errors: Db2ParseError[] = [];

    while (!this.isAtEnd()) {
      this.skipSemicolons();

      if (this.isAtEnd()) {
        break;
      }

      try {
        statements.push(this.parseStatement());
      } catch (error) {
        if (error instanceof Db2ParserError) {
          errors.push(error.toParseError());
        } else {
          const token = this.peek();
          errors.push(this.createError("Unexpected parsing failure.", token));
        }
        this.synchronize();
      }

      this.matchSymbol(";");
    }

    return { statements, errors };
  }

  private parseStatement(): Db2Statement {
    if (this.matchKeyword("SELECT")) {
      return this.parseSelect();
    }

    if (this.matchKeyword("CREATE")) {
      this.consumeKeyword("TABLE", "Expected TABLE after CREATE.");
      return this.parseCreateTable();
    }

    if (this.matchKeyword("INSERT")) {
      return this.parseInsert();
    }

    if (this.matchKeyword("DELETE")) {
      return this.parseDelete();
    }

    throw new Db2ParserError("Expected SELECT, CREATE TABLE, INSERT, or DELETE.", this.contextFromToken(this.peek()));
  }

  private parseSelect(): Db2Statement {
    const columns = this.parseSelectColumns();
    this.consumeKeyword("FROM", "Expected FROM after SELECT columns.");
    const table = this.consumeIdentifier("Expected a table name after FROM.");
    this.consumeKeyword("WHERE", "Expected WHERE in SELECT statement.");
    const where = this.parseWhereCondition();

    return { type: "Select", columns, table, where };
  }

  private parseSelectColumns(): "*" | string[] {
    if (this.matchSymbol("*")) {
      return "*";
    }

    const columns: string[] = [this.consumeIdentifier("Expected a column name after SELECT.")];

    while (this.matchSymbol(",")) {
      columns.push(this.consumeIdentifier("Expected a column name after comma."));
    }

    return columns;
  }

  private parseCreateTable(): Db2Statement {
    const table = this.consumeIdentifier("Expected a table name after CREATE TABLE.");
    this.consumeSymbol("(", "Expected ( after table name.");

    const columns: Array<{
      name: string;
      type: (typeof DB2_DATA_TYPES)[number];
      length?: number;
      index: (typeof DB2_INDEX_TYPES)[number];
      primaryKey?: boolean;
    }> = [];

    do {
      const name = this.consumeIdentifier("Expected a column name.");
      const type = this.consumeDataType("Expected a valid type (INT, FLOAT, VARCHAR, POINT).");
      const length = this.parseOptionalVarcharLength(type);
      
      let primaryKey = false;
      if (this.matchKeyword("PRIMARY")) {
        this.consumeKeyword("KEY", "Expected KEY after PRIMARY.");
        primaryKey = true;
      }

      let index: (typeof DB2_INDEX_TYPES)[number] = "DEFAULT_INDEX";

      if (this.matchKeyword("INDEX")) {
        index = this.consumeIndexType("Expected an index type after INDEX.");
      }

      columns.push({ name, type, length, index, primaryKey });
    } while (this.matchSymbol(","));

    this.consumeSymbol(")", "Expected ) after column definitions.");

    let fromFile: string | null = null;
    if (this.matchKeyword("FROM")) {
      this.consumeKeyword("FILE", "Expected FILE after FROM.");
      fromFile = this.consumeString("Expected a quoted path after FROM FILE.");
    }

    return { type: "CreateTable", table, columns, fromFile };
  }

  private parseInsert(): Db2Statement {
    this.consumeKeyword("INTO", "Expected INTO after INSERT.");
    const table = this.consumeIdentifier("Expected a table name after INTO.");
    this.consumeKeyword("VALUES", "Expected VALUES after table name.");
    this.consumeSymbol("(", "Expected ( after VALUES.");

    const values: Db2Scalar[] = [];
    do {
      values.push(this.parseLiteral("Expected a literal value in VALUES()."));
    } while (this.matchSymbol(","));

    this.consumeSymbol(")", "Expected ) after VALUES.");
    return { type: "Insert", table, values };
  }

  private parseDelete(): Db2Statement {
    this.consumeKeyword("FROM", "Expected FROM after DELETE.");
    const table = this.consumeIdentifier("Expected a table name after FROM.");
    this.consumeKeyword("WHERE", "DELETE statements must include WHERE.");
    
    const field = this.consumeIdentifier("Expected a field name in WHERE.");
    const op = this.consumeComparisonOperator("Expected a comparison operator.");
    const value = this.parseLiteral("Expected a comparison value.");
    const where: Db2WhereCondition = { type: "Comparison", field, op, value };
    
    return { type: "Delete", table, where };
  }

  private parseWhereCondition(): Db2WhereCondition {
    const field = this.consumeIdentifier("Expected a field name in WHERE.");

    if (this.matchKeyword("BETWEEN")) {
      const min = this.parseNumberLiteral("Expected minimum value after BETWEEN.");
      this.consumeKeyword("AND", "Expected AND in BETWEEN condition.");
      const max = this.parseNumberLiteral("Expected maximum value after AND.");
      return { type: "Between", field, min, max };
    }

    if (this.matchKeyword("IN")) {
      return this.parseSpatialInCondition(field);
    }

    const op = this.consumeComparisonOperator("Expected a comparison operator.");
    const value = this.parseLiteral("Expected a comparison value.");
    return { type: "Comparison", field, op, value };
  }

  private parseSpatialInCondition(field: string): Db2WhereCondition {
    this.consumeSymbol("(", "Expected ( after IN.");
    this.consumeKeyword("POINT", "IN must start with POINT(...).");
    this.consumeSymbol("(", "Expected ( after POINT.");
    const x = this.parseNumberLiteral("Expected numeric X coordinate.");
    this.consumeSymbol(",", "Expected comma between point coordinates.");
    const y = this.parseNumberLiteral("Expected numeric Y coordinate.");
    this.consumeSymbol(")", "Expected ) after point coordinates.");
    this.consumeSymbol(",", "Expected comma after POINT(...).");

    let radius: number | undefined;
    let k: number | undefined;

    if (this.matchKeyword("RADIUS")) {
      radius = this.parseNumberLiteral("Expected numeric radius.");
    } else if (this.matchKeyword("K")) {
      k = this.parseNumberLiteral("Expected numeric K value.");
    } else {
      throw new Db2ParserError("IN requires RADIUS or K after POINT.", this.contextFromToken(this.peek()));
    }

    this.consumeSymbol(")", "Expected ) after spatial IN clause.");
    return { type: "SpatialIn", field, point: [x, y], radius, k };
  }

  private parseLiteral(message: string): Db2Scalar {
    if (this.matchToken("Number")) {
      return Number(this.previous().value);
    }

    if (this.matchToken("String")) {
      return this.previous().value;
    }

    if (this.matchToken("Id")) {
      return this.previous().value;
    }

    throw new Db2ParserError(message, this.contextFromToken(this.peek()));
  }

  private parseNumberLiteral(message: string): number {
    const literal = this.parseLiteral(message);
    if (typeof literal !== "number") {
      throw new Db2ParserError(message, this.contextFromToken(this.previous()));
    }

    return literal;
  }

  private consumeIdentifier(message: string): string {
    if (this.matchToken("Id") || this.matchToken("Keyword")) {
      return this.previous().value;
    }

    throw new Db2ParserError(message, this.contextFromToken(this.peek()));
  }

  private consumeDataType(message: string): (typeof DB2_DATA_TYPES)[number] {
    const token = this.peek();
    if (token.kind === "Keyword" && DATA_TYPES.has(token.value.toUpperCase())) {
      this.advance();
      return token.value.toUpperCase() as (typeof DB2_DATA_TYPES)[number];
    }

    throw new Db2ParserError(message, this.contextFromToken(token));
  }

  private parseOptionalVarcharLength(type: (typeof DB2_DATA_TYPES)[number]): number | undefined {
    if (type !== "VARCHAR" || !this.matchSymbol("(")) {
      return undefined;
    }

    const length = this.parseNumberLiteral("Expected a numeric length inside VARCHAR(...).");

    if (!Number.isInteger(length) || length <= 0) {
      throw new Db2ParserError("VARCHAR length must be a positive integer.", this.contextFromToken(this.previous()));
    }

    this.consumeSymbol(")", "Expected ) after VARCHAR length.");
    return length;
  }

  private consumeIndexType(message: string): (typeof DB2_INDEX_TYPES)[number] {
    const token = this.peek();
    if (token.kind === "Keyword" && INDEX_TYPES.has(token.value.toUpperCase())) {
      this.advance();
      return token.value.toUpperCase() as (typeof DB2_INDEX_TYPES)[number];
    }

    throw new Db2ParserError(message, this.contextFromToken(token));
  }

  private consumeComparisonOperator(message: string): Db2ComparisonOperator {
    const token = this.peek();
    if (token.kind === "Operator" && ["=", "<", ">", "<=", ">=", "!="].includes(token.value)) {
      this.advance();
      return token.value as Db2ComparisonOperator;
    }

    throw new Db2ParserError(message, this.contextFromToken(token));
  }

  private consumeString(message: string): string {
    if (this.matchToken("String")) {
      return this.previous().value;
    }

    throw new Db2ParserError(message, this.contextFromToken(this.peek()));
  }

  private consumeKeyword(keyword: string, message: string): void {
    if (!this.matchKeyword(keyword)) {
      throw new Db2ParserError(message, this.contextFromToken(this.peek()));
    }
  }

  private consumeSymbol(symbol: string, message: string): void {
    if (!this.matchSymbol(symbol)) {
      throw new Db2ParserError(message, this.contextFromToken(this.peek()));
    }
  }

  private matchKeyword(keyword: string): boolean {
    const token = this.peek();
    if (token.kind === "Keyword" && token.value.toUpperCase() === keyword.toUpperCase()) {
      this.advance();
      return true;
    }
    return false;
  }

  private matchSymbol(symbol: string): boolean {
    const token = this.peek();
    if (token.kind === "Symbol" && token.value === symbol) {
      this.advance();
      return true;
    }
    return false;
  }

  private matchToken(kind: Db2Token["kind"]): boolean {
    if (this.peek().kind === kind) {
      this.advance();
      return true;
    }

    return false;
  }

  private skipSemicolons(): void {
    while (this.matchSymbol(";")) {
      // empty
    }
  }

  private synchronize(): void {
    this.advance();

    while (!this.isAtEnd()) {
      if (this.previous().kind === "Symbol" && this.previous().value === ";") {
        return;
      }

      if (this.peek().kind === "Symbol" && this.peek().value === ";") {
        this.advance();
        return;
      }

      this.advance();
    }
  }

  private advance(): Db2Token {
    if (!this.isAtEnd()) {
      this.current += 1;
    }

    return this.previous();
  }

  private peek(): Db2Token {
    return this.tokens[this.current] ?? this.tokens[this.tokens.length - 1];
  }

  private previous(): Db2Token {
    return this.tokens[this.current - 1] ?? this.tokens[0];
  }

  private isAtEnd(): boolean {
    return this.peek().kind === "EOF";
  }

  private contextFromToken(token: Db2Token): Db2ParseContext {
    return { line: token.line, column: token.column };
  }

  private createError(message: string, token: Db2Token): Db2ParseError {
    return {
      error: true,
      type: "SyntaxError",
      message,
      context: this.contextFromToken(token),
    };
  }
}

export function parseDb2Program(source: string): Db2Program {
  return new Db2Parser(tokenizeDb2Program(source)).parseProgram();
}

export function parseDb2Query(source: string): Db2ParseResult {
  return parseDb2Program(source);
}