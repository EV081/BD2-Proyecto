from enum import Enum, auto

class TokenType(Enum):
    # Keywords
    CREATE = auto()      # CREATE
    TABLE = auto()       # TABLE
    SELECT = auto()      # SELECT
    FROM = auto()        # FROM
    WHERE = auto()       # WHERE
    INSERT = auto()      # INSERT
    INTO = auto()        # INTO
    VALUES = auto()      # VALUES
    DELETE = auto()      # DELETE
    FILE = auto()        # FILE
    
    # Técnicas de Indexación 
    INDEX = auto()       # INDEX
    SEQUENTIAL = auto()  # SEQUENTIAL
    HASH = auto()        # HASH
    BPLUS = auto()       # BPLUS
    RTREE = auto()       # RTREE
    
    # Operadores Lógicos y Espaciales
    BETWEEN = auto()     # BETWEEN
    AND = auto()         # AND
    IN = auto()          # IN
    POINT = auto()       # POINT
    RADIUS = auto()      # RADIUS
    K = auto()           # K
    
    # Identificadores y Literales
    ID = auto()             
    NUMBER = auto()         
    STRING_LITERAL = auto() 
    
    # Operadores y Puntuación
    EQUAL = auto()       # =
    LESS = auto()        # <
    GREATER = auto()     # >
    STAR = auto()        # *
    COMMA = auto()       # ,
    LPAREN = auto()      # (
    RPAREN = auto()      # )
    SEMICOLON = auto()   # ;
    DQUOTE = auto()      # "
    QUOTE = auto()       # '
    LBRACKET = auto()    # [
    RBRACKET = auto()    # ]
    DOT = auto()         # .
    
    # Control
    EOF = auto()            
    ERROR = auto()

KEYWORDS = {
    "SELECT": TokenType.SELECT,
    "CREATE": TokenType.CREATE,
    "TABLE": TokenType.TABLE,
    "WHERE": TokenType.WHERE,
    "INSERT": TokenType.INSERT,
    "INTO": TokenType.INTO,
    "VALUES": TokenType.VALUES,
    "DELETE": TokenType.DELETE,
    "FROM": TokenType.FROM,
    "FILE": TokenType.FILE,
    "INDEX": TokenType.INDEX,
    "BETWEEN": TokenType.BETWEEN,
    "AND": TokenType.AND,
    "IN": TokenType.IN,
    "POINT": TokenType.POINT,
    "RADIUS": TokenType.RADIUS,
    "K": TokenType.K,
    "SEQUENTIAL": TokenType.SEQUENTIAL,
    "HASH": TokenType.HASH,
    "BPLUS": TokenType.BPLUS,
    "RTREE": TokenType.RTREE
}

OPERATORS = {
    ";": TokenType.SEMICOLON,
    "=": TokenType.EQUAL,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    ",": TokenType.COMMA,
    "*": TokenType.STAR,
    "<": TokenType.LESS,
    ">": TokenType.GREATER,
    "\"": TokenType.DQUOTE,
    "'": TokenType.QUOTE,
    "[": TokenType.LBRACKET,
    "]": TokenType.RBRACKET,
    ".": TokenType.DOT
}

class Token:
    def __init__(self, type: TokenType, source=None):
        self.type = type
        
        if source is not None:
            self.text = str(source)
        else:
            self.text = ""
    
    def __str__(self):
        if self.type == TokenType.EOF:
            return "TOKEN(EOF)"
        return f"TOKEN({self.type.name}, \"{self.text}\")"