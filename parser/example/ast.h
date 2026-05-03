#ifndef AST_H
#define AST_H

#include <string>
#include <unordered_map>
#include <list>
#include <ostream>

using namespace std;

class Visitor; 

// Operadores binarios soportados
enum BinaryOp { 
    PLUS_OP, 
    MINUS_OP, 
    MUL_OP, 
    DIV_OP,
    POW_OP
};

// Nuevo: Operadores unarios agregados
enum UnaryOp {
    NEGAT_OP
};



// Clase abstracta Exp
class Exp {
public:
    virtual int  accept(Visitor* visitor) = 0;
    virtual ~Exp() = 0;  // Destructor puro → clase abstracta
    static string binopToChar(BinaryOp op);  // Conversión operador → string
    static string unaopToChar(UnaryOp op);
};

// Expresión binaria
class BinaryExp : public Exp {
public:
    Exp* left;
    Exp* right;
    BinaryOp op;
    int accept(Visitor* visitor);
    BinaryExp(Exp* l, Exp* r, BinaryOp op);
    ~BinaryExp();

};


// Nuevo: Expresión unaria
class UnaryExp : public Exp {
public:
    Exp* exp;
    UnaryOp op;
    int accept(Visitor* visitor);
    UnaryExp(Exp* e, UnaryOp op);
    ~UnaryExp();
};



// Expresión numérica
class NumberExp : public Exp {
public:
    int value;
    int accept(Visitor* visitor);
    NumberExp(int v);
    ~NumberExp();
};


class IdExp : public Exp {
public:
    string value;
    int accept(Visitor* visitor);
    IdExp(string v);
    ~IdExp();
};

// Raiz cuadrada
class SqrtExp : public Exp {
public:
    Exp* value;
    int accept(Visitor* visitor);
    SqrtExp(Exp* v);
    ~SqrtExp();
}
;

class Stmt{
public:
    virtual void accept(Visitor* visitor) = 0;
    virtual ~Stmt() = 0;
};

class AsignStmt : public Stmt {
public:
    list<string> variable;
    list<Exp*> exp;
    void accept(Visitor* visitor) override;
    AsignStmt(list<string> var, list<Exp*> e);
    ~AsignStmt();
};

class PrintStmt : public Stmt {
public:
    Exp* exp;
    void accept(Visitor* visitor) override;
    PrintStmt(Exp* e);
    ~PrintStmt();
};

class Programa {
public:
    list<Stmt*> slist;
    void accept(Visitor* visitor);
    ~Programa();
    Programa();

};

/////////////////
class MaxExp : public Exp {
public:
    list<Exp*> exps;
    int accept(Visitor* visitor);
    MaxExp(list<Exp*> elist);
    ~MaxExp();
};

class IfExp : public Exp {
public:
    Exp* condition;
    Exp* thenBranch;
    Exp* elseBranch;
    int accept(Visitor* visitor);
    IfExp(Exp* cond, Exp* thenB, Exp* elseB);
    ~IfExp();
};

#endif // AST_H
