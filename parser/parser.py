from scanner import *

class ParserError(Exception):
    pass

class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.position = 0

    # Program ::= StmtList
    def parse_program(self):
        statements = []
        if not self.check(TokenType.EOF):
            statements.append(self.parse_statement())
            while self.match(TokenType.SEMICOLON):
                if self.check(TokenType.EOF):
                    break
                statements.append(self.parse_statement())
        
        self.expect(TokenType.EOF)
        return statements

    # Stmt ::= CreateStmt | SelectStmt | InsertStmt | DeleteStmt
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

    # CreateStmt ::= CREATE TABLE Id ( ColDef { , ColDef }* ) [ FROM FILE Path ]
    def parse_create_table(self):
        self.expect(TokenType.CREATE)
        self.expect(TokenType.TABLE)

        table_name = self.expect(TokenType.ID).text
        self.expect(TokenType.LPAREN)

        columns = [self.parse_column_def()]
        while self.match(TokenType.COMMA):
            columns.append(self.parse_column_def())

        self.expect(TokenType.RPAREN)

        file_path = None
        if self.match(TokenType.FROM):
            self.expect(TokenType.FILE)
            file_path = self.parse_path_value()

        return {
            "type": "create_table",
            "name": table_name,
            "columns": columns,
            "file": file_path,
        }

    # ColDef ::= Id Type [ INDEX IndexTech ]
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

    # SelectStmt ::= SELECT Cols FROM Id [ WHERE Condition ]
    def parse_select(self):
        self.expect(TokenType.SELECT)
        columns = self.parse_select_columns()
        self.expect(TokenType.FROM)
        table_name = self.expect(TokenType.ID).text
        
        condition = None
        if self.match(TokenType.WHERE):
            condition = self.parse_condition()

        return {
            "type": "select",
            "columns": columns,
            "table": table_name,
            "where": condition,
        }

    # Cols ::= * | Id { , Id }*
    def parse_select_columns(self):
        if self.match(TokenType.STAR):
            return ["*"]

        columns = [self.expect(TokenType.ID).text]
        while self.match(TokenType.COMMA):
            columns.append(self.expect(TokenType.ID).text)

        return columns

    # InsertStmt ::= INSERT INTO Id VALUES ( Value { , Value }* )
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
        return {
            "type": "insert",
            "table": table_name,
            "values": values,
        }

    # DeleteStmt ::= DELETE FROM Id WHERE Id RelOp Value
    def parse_delete(self):
        self.expect(TokenType.DELETE)
        self.expect(TokenType.FROM)
        table_name = self.expect(TokenType.ID).text
        
        self.expect(TokenType.WHERE)
        left_id = self.expect(TokenType.ID).text
        rel_op = self.parse_relop()
        right_value = self.parse_value()
        
        return {
            "type": "delete",
            "table": table_name,
            "where": {
                "type": "comparison",
                "left": left_id,
                "operator": rel_op,
                "right": right_value
            }
        }

    # Condition ::= Id RelOp Value | Id BETWEEN Value AND Value | Id IN ( SpatialCond )
    def parse_condition(self):
        left_id = self.expect(TokenType.ID).text
        
        if self.match(TokenType.BETWEEN):
            lower = self.parse_value()
            self.expect(TokenType.AND)
            upper = self.parse_value()
            return {
                "type": "between",
                "left": left_id,
                "lower": lower,
                "upper": upper,
            }
            
        if self.match(TokenType.IN):
            self.expect(TokenType.LPAREN)
            spatial_cond = self.parse_spatial_cond()
            self.expect(TokenType.RPAREN)
            return {
                "type": "in_spatial",
                "left": left_id,
                "spatial_condition": spatial_cond
            }

        rel_op = self.parse_relop()
        right_value = self.parse_value()
        return {
            "type": "comparison",
            "left": left_id,
            "operator": rel_op,
            "right": right_value,
        }

    # SpatialCond ::= POINT ( Number , Number ) , ( RADIUS Number | K Number )
    def parse_spatial_cond(self):
        self.expect(TokenType.POINT)
        self.expect(TokenType.LPAREN)
        
        x_neg = self.match(TokenType.MINUS)
        x_val = self.expect(TokenType.NUMBER).text
        x = -float(x_val) if x_neg else float(x_val)
        
        self.expect(TokenType.COMMA)
        
        y_neg = self.match(TokenType.MINUS)
        y_val = self.expect(TokenType.NUMBER).text
        y = -float(y_val) if y_neg else float(y_val)
        
        self.expect(TokenType.RPAREN)
        self.expect(TokenType.COMMA)
        
        spatial_type = None
        radius_or_k_val = None
        
        if self.match(TokenType.RADIUS):
            spatial_type = "radius"
            radius_or_k_val = float(self.expect(TokenType.NUMBER).text)
        elif self.match(TokenType.K):
            spatial_type = "k"
            radius_or_k_val = int(self.expect(TokenType.NUMBER).text)
        else:
            raise ParserError("Se esperaba RADIUS o K dentro de la condicion espacial")

        return {
            "type": "spatial_point",
            "x": x,
            "y": y,
            "search_type": spatial_type,
            "search_value": radius_or_k_val
        }

    # RelOp ::= = | < | > | <= | >= | !=
    def parse_relop(self):
        token = self.consume()
        if token is None or token.type not in (
            TokenType.EQUAL, TokenType.LESS, TokenType.GREATER, 
            TokenType.LESS_EQUAL, TokenType.GREATER_EQUAL, TokenType.NOT_EQUAL
        ):
            raise ParserError("Se esperaba un operador relacional (=, <, >, <=, >=, !=)")
        return token.text

    # Type ::= INT | FLOAT | VARCHAR | POINT
    def parse_type_token(self):
        token = self.consume()
        if token is None or token.type not in (TokenType.INT, TokenType.FLOAT, TokenType.VARCHAR, TokenType.POINT):
            raise ParserError(f"Tipo de dato no soportado: {token}")
            
        if token.type == TokenType.VARCHAR and self.check(TokenType.LPAREN):
            self.consume()
            size = self.expect(TokenType.NUMBER).text
            self.expect(TokenType.RPAREN)
            return f"{token.text}({size})"
            
        return token.text

    # IndexTech ::= SEQUENTIAL | HASH | BTREE | RTREE
    def parse_index_technique(self):
        token = self.consume()
        if token is None or token.type not in (TokenType.SEQUENTIAL, TokenType.HASH, TokenType.BTREE, TokenType.RTREE):
            raise ParserError(f"Tecnica de indexacion no soportada: {token}")
        return token.text

    # Value ::= Number | String
    def parse_value(self):
        is_negative = False
        if self.match(TokenType.MINUS):
            is_negative = True
            
        token = self.consume()
        if token is None:
            raise ParserError("Se esperaba un valor")
        
        if token.type == TokenType.NUMBER:
            val = int(token.text) if token.text.isdigit() else float(token.text)
            return -val if is_negative else val
            
        if token.type in (TokenType.STRING_LITERAL, TokenType.ID):
            if is_negative:
                raise ParserError("Un texto no puede ser negativo")
            return token.text

        raise ParserError(f"Valor no soportado: {token}")

    def parse_path_value(self):
        token = self.consume()
        if token is None or token.type not in (TokenType.STRING_LITERAL, TokenType.ID):
            raise ParserError("Se esperaba una ruta de archivo")
        return token.text

    # --- Funciones de utilidad de consumo ---
    def peek(self):
        if self.position < len(self.tokens):
            return self.tokens[self.position]
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