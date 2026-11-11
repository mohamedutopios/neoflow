package com.neosoft.neoflow.legacyia.analyse;

import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.expr.BinaryExpr;
import com.github.javaparser.ast.expr.ConditionalExpr;
import com.github.javaparser.ast.stmt.CatchClause;
import com.github.javaparser.ast.stmt.DoStmt;
import com.github.javaparser.ast.stmt.ForEachStmt;
import com.github.javaparser.ast.stmt.ForStmt;
import com.github.javaparser.ast.stmt.IfStmt;
import com.github.javaparser.ast.stmt.SwitchEntry;
import com.github.javaparser.ast.stmt.WhileStmt;

/**
 * Complexité cyclomatique de McCabe : 1 + nombre de points de décision.
 *
 * <p>Points comptés (convention de lizard et de Checkstyle) : {@code if} (un {@code else if} est un
 * {@code if}), {@code for}, for-each, {@code while}, {@code do}, {@code catch}, opérateur ternaire,
 * {@code case} (une branche {@code case A, B ->} compte une fois, {@code default} ne compte pas),
 * {@code &&} et {@code ||}. Sur le legacy NeoFlow : {@code determinerNiveau} = 28, {@code calculer} = 10.
 */
public final class ComplexiteCyclomatique {

    private ComplexiteCyclomatique() {
    }

    /**
     * @param corps déclaration de méthode ou de constructeur (ou tout nœud)
     * @return complexité, au moins 1
     */
    public static int calculer(Node corps) {
        // TODO TP1-1 : compter les points de décision avec corps.findAll(...) :
        //   IfStmt, ForStmt, ForEachStmt, WhileStmt, DoStmt, CatchClause, ConditionalExpr,
        //   SwitchEntry dont getLabels() n'est pas vide (default ne compte pas),
        //   BinaryExpr d'opérateur AND ou OR.
        // Attendu sur le legacy : determinerNiveau = 28, calculer = 10 (AnalyseurLegacyTest.Complexite).
        return 1;
    }
}
