#ifndef PARSER_H       
#define PARSER_H

#include "scanner.h"    // Incluye la definición del escáner (provee tokens al parser)
#include "ast.h"        // Incluye las definiciones para construir el Árbol de Sintaxis Abstracta (AST)

class Parser {
private:
    Scanner* scanner;       // Puntero al escáner, de donde se leen los tokens
    Token *current, *previous; // Punteros al token actual y al anterior
    bool match(Token::Type ttype);   // Verifica si el token actual coincide con un tipo esperado y avanza si es así
    bool check(Token::Type ttype);   // Comprueba si el token actual es de cierto tipo, sin avanzar
    bool advance();                  // Avanza al siguiente token
    bool isAtEnd();                  // Comprueba si ya se llegó al final de la entrada
public:
    Parser(Scanner* scanner);       
    Programa* parseProgram();             // Punto de entrada: analiza un programa completo
    Programa* parseP();
    Stmt* parsestmt();
    Exp* parseCEXP();                   // Regla gramatical P
    Exp* parseE();                   // Regla gramatical E
    Exp* parseT();                   // Regla gramatical T
    Exp* parseF();                   // Regla gramatical F
};

#endif // PARSER_H      