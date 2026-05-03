#include "ast.h"
#include <iostream>

using namespace std;

// ------------------ Exp ------------------
Exp::~Exp() {}

string Exp::binopToChar(BinaryOp op) {
    switch (op) {
        case PLUS_OP:  return "+";
        case MINUS_OP: return "-";
        case MUL_OP:   return "*";
        case DIV_OP:   return "/";
        case POW_OP:   return "**";
        default:       return "?";
    }
}


// Nuevo: unaopToChar
string Exp::unaopToChar(UnaryOp op) {
    switch (op) {
        case NEGAT_OP: return "-";
        default:       return "?";
    }
}


// ------------------ BinaryExp ------------------
BinaryExp::BinaryExp(Exp* l, Exp* r, BinaryOp o)
    : left(l), right(r), op(o) {}

    
BinaryExp::~BinaryExp() {
    delete left;
    delete right;
}



// ------------------ NumberExp ------------------
NumberExp::NumberExp(int v) : value(v) {}

NumberExp::~NumberExp() {}


// ------------------ SqrtExp ------------------
SqrtExp::SqrtExp(Exp* v) : value(v) {}

SqrtExp::~SqrtExp() {}

//
Programa::Programa() {}
Programa::~Programa(){}

Stmt::~Stmt(){}

PrintStmt::PrintStmt(Exp* e) {
    exp=e;
}

PrintStmt::~PrintStmt() {

}

AsignStmt::AsignStmt(list<string> texto, list<Exp*> e) {
    variable=  texto;
    exp = e;
}

AsignStmt::~AsignStmt() {
    for(auto a : exp) {
        delete a;
    }
}

// ------------------ NumberExp ------------------
IdExp::IdExp(string v) : value(v) {}

IdExp::~IdExp() {}


//////////////
MaxExp::MaxExp(list<Exp*> elist) {exps = elist;}
MaxExp::~MaxExp() {
    for (auto e : exps) {
        delete e;
    }
}
IfExp::IfExp(Exp* cond, Exp* thenB, Exp* elseB) : condition(cond), thenBranch(thenB), elseBranch(elseB) {}
IfExp::~IfExp() {}

// Nuevo: ------------------ UnaryExp ------------------
UnaryExp::UnaryExp(Exp* e, UnaryOp o)
    : exp(e), op(o) {}

    
UnaryExp::~UnaryExp() {
    delete exp;
}


