#include <iostream>
#include <fstream>
#include <cmath>
#include "ast.h"
#include "visitor.h"


using namespace std;

///////////////////////////////////////////////////////////////////////////////////
int BinaryExp::accept(Visitor* visitor) {
    return visitor->visit(this);
}

int NumberExp::accept(Visitor* visitor) {
    return visitor->visit(this);
}

int IdExp::accept(Visitor* visitor) {
    return visitor->visit(this);
}

int SqrtExp::accept(Visitor* visitor) {
    return visitor->visit(this);
}

void PrintStmt::accept(Visitor* visitor) {
    visitor->visit(this);
}

void AsignStmt::accept(Visitor* visitor) {
    visitor->visit(this);
}

void Programa::accept(Visitor* visitor) {
    visitor->visit(this);
}

int IfExp::accept(Visitor* visitor) {
    return visitor->visit(this);
}

int MaxExp::accept(Visitor* visitor) {
    return visitor->visit(this);
}
// Nuevo accept UnaryExp
int UnaryExp::accept(Visitor* visitor) {
    return visitor->visit(this);
}



///////////////////////////////////////////////////////////////////////////////////

int PrintVisitor::visit(BinaryExp* exp) {
    exp->left->accept(this);
    cout << ' ' << Exp::binopToChar(exp->op) << ' ';
    exp->right->accept(this);
    return 0;
}

int PrintVisitor::visit(NumberExp* exp) {
    cout << exp->value;
    return 0;
}

int PrintVisitor::visit(SqrtExp* exp) {
    cout << "sqrt(";
    exp->value->accept(this);
    cout <<  ")";
    return 0;
}


void PrintVisitor::imprimir(Programa* programa){
    if (programa)
    {
        cout << "Codigo:" << endl;
        programa->accept(this);
        cout << endl;
    }
    return ;
}

/////////////////
int PrintVisitor::visit(MaxExp *exp) {
    cout << "max ( ";
    for (auto it = exp->exps.begin(); it != exp->exps.end(); ++it) {
        (*it)->accept(this);
        if (next(it) != exp->exps.end()) {
            cout << ", ";
        }
    }
    cout << " ) ";
    return 0;
}

int PrintVisitor::visit(IfExp *exp) {
    cout << "if (";
    exp->condition->accept(this);
    cout << ") then (";
    exp->thenBranch->accept(this);
    cout << ") else (";
    exp->elseBranch->accept(this);
    cout << ")";
    return 0;
}


///////////////////////////////////////////////////////////////////////////////////
int EVALVisitor::visit(BinaryExp* exp) {
    int result;
    int v1 = exp->left->accept(this);
    int v2 = exp->right->accept(this);
    switch (exp->op) {
        case PLUS_OP:
            result = v1 + v2;
            break;
        case MINUS_OP:
            result = v1 - v2;
            break;
        case MUL_OP:
            result = v1 * v2;
            break;
        case DIV_OP:
            if (v2 != 0)
                result = v1 / v2;
            else {
                cout << "Error: división por cero" << endl;
                result = 0;
            }
            break;
        case POW_OP:
            result = pow(v1,v2);
            break;
        default:
            cout << "Operador desconocido" << endl;
            result = 0;
    }
    return result;
}

int EVALVisitor::visit(NumberExp* exp) {
    return exp->value;
}

int EVALVisitor::visit(SqrtExp* exp) {
    return floor(sqrt( exp->value->accept(this)));
}


void EVALVisitor::interprete(Programa* programa){
    if (programa)
    {
        cout << "Interprete:";
        programa->accept(this);
        cout <<endl;
    }
    return;
}

void EVALVisitor::visit(AsignStmt *stm) {
    auto itVar = stm->variable.begin();
    auto itExp = stm->exp.begin();
    for (; itVar != stm->variable.end() && itExp != stm->exp.end(); ++itVar, ++itExp) {
        memoria[*itVar] = (*itExp)->accept(this);
    }
}

int EVALVisitor::visit(IdExp *e) {
    return memoria[e->value];
}


void EVALVisitor::visit(PrintStmt *stm) {
    cout << stm->exp->accept(this);
}

void EVALVisitor::visit(Programa *p) {
    for (auto i:p->slist) {
        i->accept(this);
    }
}

void PrintVisitor::visit(AsignStmt *stm) {
    // variables
    for (auto it = stm->variable.begin(); it != stm->variable.end(); ++it) {
        cout << *it;
        if (next(it) != stm->variable.end()) {
            cout << ",";
        }
    }

    cout << "=";

    // expresiones
    for (auto it = stm->exp.begin(); it != stm->exp.end(); ++it) {
        (*it)->accept(this);
        if (next(it) != stm->exp.end()) {
            cout << ",";
        }
    }
    cout<<endl;
}


void PrintVisitor::visit(PrintStmt *stm) {
    cout << "print (";
    stm->exp->accept(this);
    cout << ")"<< endl;
}

void PrintVisitor::visit(Programa * p) {
    for (auto i:p->slist) {
        i->accept(this);
    }
}

int PrintVisitor::visit(IdExp *e) {
    cout << e->value;
    return 0;
}

/////////////

int EVALVisitor::visit(MaxExp *exp) {
    int max = -1e9;
    for (auto it = exp->exps.begin(); it != exp->exps.end(); ++it) {
        int v = (*it)->accept(this);
        max = max < v ? v : max;
    }
    return max;
}

int EVALVisitor::visit(IfExp *exp) {
    int cond = exp->condition->accept(this);
    if (cond) {
        return exp->thenBranch->accept(this);
    } else {
        return exp->elseBranch->accept(this);
    }
}

// Nuevo: UnaryExp visit
int PrintVisitor::visit(UnaryExp* e) {
    cout << ' ' << Exp::unaopToChar(e->op) << ' ';
    e->exp->accept(this);
    cout<< endl;
    return 0;
}

// Nuevo: UnaryExp visit
int EVALVisitor::visit(UnaryExp* e) {
    int result;
    int v = e->exp->accept(this);
    switch (e->op) {
        case NEGAT_OP:
            result = -1 * v;
            break;
        default:
            cout << "Operador desconocido" << endl;
            result = 0;
    }
    return result;
}

