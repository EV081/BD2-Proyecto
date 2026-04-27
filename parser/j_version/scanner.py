from lexer_token import *

class Scanner:
    def __init__(self, input_str):
        self.input = input_str
        self.current = 0
        
    def is_white_space(self, c):
        return c in (' ', '\n', '\r', '\t')
    
    def next_token(self):
        # saltar espacios en blanco
        while self.current < len(self.input) and self.is_white_space(self.input[self.current]):
            self.current +=1
        
        # fin de entrada
        if self.current >= len(self.input):
            return Token(TokenType.EOF)
        
        first = self.current
        char = self.input[self.current]
        
        # números
        if char.isdigit():
            while self.current < len(self.input) and self.input[self.current].isdigit():
                self.current +=1
            return Token(TokenType.NUMBER, self.input[first:self.current])

        # cadenas entre comillas simples o dobles
        if char in ('"', "'"):
            quote = char
            self.current += 1
            start = self.current

            while self.current < len(self.input) and self.input[self.current] != quote:
                self.current += 1

            if self.current >= len(self.input):
                return Token(TokenType.ERROR, self.input[first:self.current])

            text = self.input[start:self.current]
            self.current += 1
            return Token(TokenType.STRING_LITERAL, text)
        
        # ids y keywords
        if char.isalpha() or char == '_':
            while self.current < len(self.input) and (self.input[self.current].isalnum() or self.input[self.current] == '_'):
                self.current +=1
            lexema = self.input[first:self.current].upper()
            tipo = KEYWORDS.get(lexema, TokenType.ID)
            return Token(tipo, lexema)
        
        # operadores de un solo caracter
        if char in OPERATORS:
            tipo = OPERATORS.get(char)
            self.current +=1
            return Token(tipo, char)
        # caracter invalido
        else:
            self.current +=1
            return Token(TokenType.ERROR, char)
        


def execute_scanner(scanner, inputFile):
    inputFileName = inputFile.split(".")[0];
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