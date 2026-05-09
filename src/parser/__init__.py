"""Parser SQL del proyecto BD2.

Expone una API modular para reutilizar el parser desde CLI o FastAPI.
"""

from .main import moduled_main, execute_parser, collect_tokens
from .parser import Parser, ParserError
from .scanner import Scanner
from .db_visitor import DBVisitor
from .visitor import PrintVisitor, ExecuteVisitor
from .lexer_token import Token, TokenType

