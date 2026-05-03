from lexer_token import *

class Scanner:
    def __init__(self, input_str):
        self.input = input_str
        self.current = 0

    def is_white_space(self, c):
        return c in (' ', '\n', '\r', '\t')

    def next_token(self):
        # Saltar espacios en blanco
        while self.current < len(self.input) and self.is_white_space(self.input[self.current]):
            self.current += 1

        # Fin de entrada
        if self.current >= len(self.input):
            return Token(TokenType.EOF)

        first = self.current
        char = self.input[self.current]

        # Reconocimiento de String Literals ("texto" o 'texto')
        if char in ('"', "'"):
            quote_type = char
            self.current += 1
            start_str = self.current
            while self.current < len(self.input) and self.input[self.current] != quote_type:
                self.current += 1
            
            if self.current >= len(self.input):
                return Token(TokenType.ERROR, "String sin cerrar")
            
            str_val = self.input[start_str:self.current]
            self.current += 1
            return Token(TokenType.STRING_LITERAL, str_val)

        # Reconocimiento de números
        if char.isdigit():
            while self.current < len(self.input) and self.input[self.current].isdigit():
                self.current += 1
            
            if self.current < len(self.input) and self.input[self.current] == '.':
                self.current += 1
                while self.current < len(self.input) and self.input[self.current].isdigit():
                    self.current += 1
                    
            return Token(TokenType.NUMBER, self.input[first:self.current])

        # IDs y Keywords
        if char.isalpha() or char == '_':
            while self.current < len(self.input) and (self.input[self.current].isalnum() or self.input[self.current] == '_'):
                self.current += 1
            lexema = self.input[first:self.current]
            
            tipo = KEYWORDS.get(lexema.upper(), TokenType.ID)
            
            if tipo == TokenType.ID:
                return Token(tipo, lexema)
            return Token(tipo, lexema.upper())

        # Reconocimiento de operadores
        if self.current + 1 < len(self.input):
            lexema_doble = self.input[first:self.current + 2]
            if lexema_doble in OPERATORS:
                self.current += 2
                tipo = OPERATORS.get(lexema_doble)
                return Token(tipo, lexema_doble)

        if char in OPERATORS:
            tipo = OPERATORS.get(char)
            self.current += 1
            return Token(tipo, char)

        # Caracter inválido
        else:
            self.current += 1
            return Token(TokenType.ERROR, char)

def execute_scanner(scanner, inputFile, output_dir=None):
    import os
    base_name = os.path.basename(inputFile)
    name, _ = os.path.splitext(base_name)
    
    if output_dir:
        if name.startswith("input"):
            idx = name[5:]
            OutputFileName = os.path.join(output_dir, f"tokens_{idx}.txt")
        else:
            OutputFileName = os.path.join(output_dir, f"{name}_token.txt")
    else:
        inputFileName, _ = os.path.splitext(inputFile)
        OutputFileName = f"{inputFileName}_token.txt"
    
    try:
        with open(OutputFileName, 'w', encoding='utf-8') as out_file:
            out_file.write("Scanner\n\n")
            while True:
                tok = scanner.next_token()
                if tok.type == TokenType.EOF:
                    out_file.write(f"{tok}\n")
                    out_file.write("\nScanner exitoso\n\n")
                    return
                if tok.type == TokenType.ERROR:
                    out_file.write(f"{tok}\n")
                    out_file.write("Caracter invalido\n\n")
                    out_file.write("Scanner no exitoso\n\n")
                    return
                out_file.write(f"{tok}\n")
    except IOError as e:
        print(f"Error: no se pudo abrir el archivo {OutputFileName}: {e}")