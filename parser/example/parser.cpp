#include <iostream>
#include <stdexcept>
#include "token.h"
#include "scanner.h"
#include "ast.h"
#include "parser.h"

using namespace std;

// =============================
// Métodos de la clase Parser
// =============================

Parser::Parser(Scanner* sc) : scanner(sc) {
    previous = nullptr;
    current = scanner->nextToken();
    if (current->type == Token::ERR) {
        throw runtime_error("Error léxico");
    }
}

bool Parser::match(Token::Type ttype) {
    if (check(ttype)) {
        advance();
        return true;
    }
    return false;
}

bool Parser::check(Token::Type ttype) {
    if (isAtEnd()) return false;
    return current->type == ttype;
}

bool Parser::advance() {
    if (!isAtEnd()) {
        Token* temp = current;
        if (previous) delete previous;
        current = scanner->nextToken();
        previous = temp;

        if (check(Token::ERR)) {
            throw runtime_error("Error lexico");
        }
        return true;
    }
    return false;
}

bool Parser::isAtEnd() {
    return (current->type == Token::END);
}


// =============================
// Reglas gramaticales
// =============================

Programa* Parser::parseProgram() {
    Programa* ast = parseP();
    if (!isAtEnd()) {
        throw runtime_error("Error sintáctico");
    }
    cout << "Parseo exitoso" << endl;
    return ast;
}

Programa* Parser::parseP() {
    Programa* p =  new Programa();
    p->slist.push_back(parsestmt());
    while (match(Token::SEMICOL)) {
        p->slist.push_back(parsestmt());
    }
    return p;
}

Stmt *Parser::parsestmt() {
    Exp* e;
    if (match(Token::PRINT)) {
        match(Token::LPAREN);
        e = parseCEXP();
        match(Token::RPAREN);
        return new PrintStmt(e);
    }
    else if (match(Token::ID)) {
        list<string> variable;
        list<Exp*> exp;

        variable.push_back(previous->text);
        while (match(Token::COMA)) {
            match(Token::ID);
            variable.push_back(previous->text);
        }

        match(Token::ASSIGN);

        exp.push_back(parseCEXP());
        while (match(Token::COMA)) {
            exp.push_back(parseCEXP());
        }

        return new AsignStmt(variable, exp);
    }
}


Exp* Parser::parseCEXP() {
    Exp* l = parseE();
    while (match(Token::PLUS) || match(Token::MINUS)) {
        BinaryOp op;
        if (previous->type == Token::PLUS){
            op = PLUS_OP;
        }
        else{
            op = MINUS_OP;
        }
        Exp* r = parseE();
        l = new BinaryExp(l, r, op);
    }
    return l;
}



Exp* Parser::parseE() {
    Exp* l = parseT();
    while (match(Token::MUL) || match(Token::DIV)) {
        BinaryOp op;
        if (previous->type == Token::MUL){
            op = MUL_OP;
        }
        else{
            op = DIV_OP;
        }
        Exp* r = parseT();
        l = new BinaryExp(l, r, op);
    }
    return l;
}


Exp* Parser::parseT() {
    Exp* l = parseF();
    if (match(Token::POW)) {
        BinaryOp op = POW_OP;
        Exp* r = parseF();
        l = new BinaryExp(l, r, op);
    }
    return l;
}

Exp* Parser::parseF() {
    Exp* e; 
    if (match(Token::NUM)) {
        return new NumberExp(stoi(previous->text));
    }
    else if (match(Token::ID)) {
        return new IdExp(previous->text);
    }
    else if (match(Token::LPAREN))
    {
        e = parseCEXP();
        match(Token::RPAREN);
        return e;
    }
    else if (match(Token::SQRT))
    {   
        match(Token::LPAREN);
        e = parseCEXP();
        match(Token::RPAREN);
        return new SqrtExp(e);
    }
    else if (match(Token::MAX))
    {
        match(Token::LPAREN);
        list<Exp*> elist;
        elist.push_back(parseCEXP());
        while (match(Token::COMA)) {
            elist.push_back(parseCEXP());
        }
        match(Token::RPAREN);
        return new MaxExp(elist);
    }
    else if (match(Token::IFEXP))
    {
        match(Token::LPAREN);
        Exp* condition = parseCEXP();
        match(Token::COMA);
        Exp* thenBranch = parseCEXP();
        match(Token::COMA);
        Exp* elseBranch = parseCEXP();
        match(Token::RPAREN);
        return new IfExp(condition, thenBranch, elseBranch);
    }
    // Nuevo: Matching Minus en F del parser
    else if (match(Token::MINUS))
    {
        UnaryOp op = NEGAT_OP;
        match(Token::LPAREN);
        e = parseCEXP();
        match(Token::RPAREN);
        return new UnaryExp(e, op);
    }

    else {
        throw runtime_error("Error sintáctico");
    }
}

// x = 5; print(x)
