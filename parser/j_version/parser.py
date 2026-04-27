from scanner import *


class ParserError(Exception):
    pass


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.position = 0

    def parse(self):
        statement = self.parse_statement()
        self.expect(TokenType.EOF)
        return statement

    def parse_statement(self):
        token = self.peek()

        if token is None:
            raise ParserError("Entrada vacia")

        if token.type == TokenType.CREATE:
            return self.parse_create_table()
        if token.type == TokenType.SELECT:
            return self.parse_select()
        if token.type == TokenType.INSERT:
            return self.parse_insert()
        if token.type == TokenType.DELETE:
            return self.parse_delete()

        raise ParserError(f"Sentencia no soportada: {token}")

    def parse_create_table(self):
        self.expect(TokenType.CREATE)
        self.expect(TokenType.TABLE)

        table_name = self.expect(TokenType.ID).text
        self.expect(TokenType.LPAREN)

        body = self.parse_create_body()
        self.expect(TokenType.RPAREN)

        file_path = None
        if self.match(TokenType.FROM):
            if self.match(TokenType.FILE):
                file_path = self.parse_path_value()
            else:
                file_path = self.parse_path_value()
        elif self.check(TokenType.STRING_LITERAL):
            file_path = self.parse_path_value()

        self.expect(TokenType.SEMICOLON)

        return {
            "type": "create_table",
            "name": table_name,
            "body": body,
            "file": file_path,
        }

    def parse_create_body(self):
        if self.check(TokenType.NUMBER):
            return self.parse_legacy_create_body()

        columns = [self.parse_column_def()]
        while self.match(TokenType.COMMA):
            columns.append(self.parse_column_def())

        return {
            "mode": "columns",
            "columns": columns,
        }

    def parse_legacy_create_body(self):
        column_count = self.expect(TokenType.NUMBER).text
        technique = self.parse_index_technique()

        override_index = None
        if self.match(TokenType.LBRACKET):
            self.expect(TokenType.INDEX)
            override_index = self.parse_index_technique()
            self.expect(TokenType.RBRACKET)

        return {
            "mode": "legacy",
            "column_count": int(column_count),
            "technique": technique,
            "override_index": override_index,
        }

    def parse_column_def(self):
        name = self.expect(TokenType.ID).text
        data_type = self.parse_type_token()

        index = None
        if self.match(TokenType.INDEX):
            index = self.parse_index_technique()

        return {
            "name": name,
            "data_type": data_type,
            "index": index,
        }

    def parse_select(self):
        self.expect(TokenType.SELECT)
        columns = self.parse_select_columns()
        self.expect(TokenType.FROM)

        table_name = self.expect(TokenType.ID).text
        where = None

        if self.match(TokenType.WHERE):
            where = self.parse_condition()

        self.expect(TokenType.SEMICOLON)
        return {
            "type": "select",
            "columns": columns,
            "table": table_name,
            "where": where,
        }

    def parse_select_columns(self):
        if self.match(TokenType.STAR):
            return ["*"]

        columns = [self.expect(TokenType.ID).text]
        while self.match(TokenType.COMMA):
            columns.append(self.expect(TokenType.ID).text)

        return columns

    def parse_insert(self):
        self.expect(TokenType.INSERT)
        self.expect(TokenType.INTO)
        table_name = self.expect(TokenType.ID).text
        self.expect(TokenType.VALUES)
        self.expect(TokenType.LPAREN)

        values = [self.parse_value()]
        while self.match(TokenType.COMMA):
            values.append(self.parse_value())

        self.expect(TokenType.RPAREN)
        self.expect(TokenType.SEMICOLON)
        return {
            "type": "insert",
            "table": table_name,
            "values": values,
        }

    def parse_delete(self):
        self.expect(TokenType.DELETE)
        self.expect(TokenType.FROM)
        table_name = self.expect(TokenType.ID).text
        self.expect(TokenType.WHERE)

        condition = self.parse_comparison()
        self.expect(TokenType.SEMICOLON)
        return {
            "type": "delete",
            "table": table_name,
            "where": condition,
        }

    def parse_condition(self):
        token = self.peek()

        if token is None:
            raise ParserError("Se esperaba una condicion")

        if token.type != TokenType.ID:
            raise ParserError(f"Se esperaba un identificador en la condicion, se encontro {token}")

        next_token = self.peek_next()
        if next_token is None:
            raise ParserError("Condicion incompleta")

        if next_token.type == TokenType.BETWEEN:
            return self.parse_between()
        if next_token.type == TokenType.IN:
            return self.parse_in_condition()
        if next_token.type in (TokenType.EQUAL, TokenType.LESS, TokenType.GREATER):
            return self.parse_comparison()

        raise ParserError(f"Operador de condicion no soportado: {next_token}")

    def parse_comparison(self):
        left = self.expect(TokenType.ID).text
        operator_token = self.consume()

        if operator_token is None or operator_token.type not in (TokenType.EQUAL, TokenType.LESS, TokenType.GREATER):
            raise ParserError("Se esperaba un operador de comparacion (=, < o >)")

        right = self.parse_value()
        return {
            "type": "comparison",
            "left": left,
            "operator": operator_token.text,
            "right": right,
        }

    def parse_between(self):
        left = self.expect(TokenType.ID).text
        self.expect(TokenType.BETWEEN)
        lower = self.parse_value()
        self.expect(TokenType.AND)
        upper = self.parse_value()

        return {
            "type": "between",
            "left": left,
            "lower": lower,
            "upper": upper,
        }

    def parse_in_condition(self):
        left = self.expect(TokenType.ID).text
        self.expect(TokenType.IN)
        self.expect(TokenType.LPAREN)

        values = [self.parse_in_value()]
        while self.match(TokenType.COMMA):
            values.append(self.parse_in_value())

        self.expect(TokenType.RPAREN)
        return {
            "type": "in",
            "left": left,
            "values": values,
        }

    def parse_in_value(self):
        token = self.peek()

        if token is None:
            raise ParserError("Se esperaba un valor dentro de IN")

        if token.type == TokenType.POINT:
            return self.parse_point_predicate()
        if token.type in (TokenType.RADIUS, TokenType.K):
            return self.parse_spatial_predicate()

        raise ParserError(f"Predicado IN no soportado: {token}")

    def parse_point_predicate(self):
        self.expect(TokenType.POINT)
        self.expect(TokenType.LPAREN)
        x = self.expect(TokenType.NUMBER).text
        self.expect(TokenType.COMMA)
        y = self.expect(TokenType.NUMBER).text
        self.expect(TokenType.RPAREN)

        return {
            "type": "point",
            "x": int(x),
            "y": int(y),
        }

    def parse_spatial_predicate(self):
        token = self.consume()
        value = self.expect(TokenType.NUMBER).text

        return {
            "type": token.type.name.lower(),
            "value": int(value),
        }

    def parse_value(self):
        token = self.consume()

        if token is None:
            raise ParserError("Se esperaba un valor")

        if token.type == TokenType.NUMBER:
            return int(token.text)
        if token.type in (TokenType.STRING_LITERAL, TokenType.ID):
            return token.text

        raise ParserError(f"Valor no soportado: {token}")

    def parse_path_value(self):
        token = self.consume()

        if token is None:
            raise ParserError("Se esperaba una ruta de archivo")

        if token.type in (TokenType.STRING_LITERAL, TokenType.ID):
            return token.text

        raise ParserError(f"Ruta de archivo no soportada: {token}")

    def parse_type_token(self):
        token = self.consume()

        if token is None:
            raise ParserError("Se esperaba un tipo de dato")

        if token.type in (TokenType.ID, TokenType.NUMBER):
            return token.text

        raise ParserError(f"Tipo de dato no soportado: {token}")

    def parse_index_technique(self):
        token = self.consume()

        if token is None:
            raise ParserError("Se esperaba una tecnica de indexacion")

        if token.type in (TokenType.SEQUENTIAL, TokenType.HASH, TokenType.BPLUS, TokenType.RTREE):
            return token.type.name

        raise ParserError(f"Tecnica de indexacion no soportada: {token}")

    def peek(self):
        if self.position < len(self.tokens):
            return self.tokens[self.position]
        return None

    def peek_next(self):
        next_position = self.position + 1
        if next_position < len(self.tokens):
            return self.tokens[next_position]
        return None

    def check(self, token_type):
        token = self.peek()
        return token is not None and token.type == token_type

    def match(self, token_type):
        if self.check(token_type):
            self.consume()
            return True
        return False

    def expect(self, token_type):
        token = self.consume()

        if token is None:
            raise ParserError(f"Se esperaba {token_type.name} pero la entrada termino antes")

        if token.type != token_type:
            raise ParserError(f"Se esperaba {token_type.name} y se encontro {token.type.name}")

        return token

    def consume(self):
        token = self.peek()
        if token is not None:
            self.position += 1
        return token    