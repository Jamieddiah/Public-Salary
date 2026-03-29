"""
SIRH — Moteur d'Avancement et de Validation
Administration Publique Sénégalaise

Gère :
  - La mise en solde (enregistrement initial)
  - La validation des services antérieurs
  - Le calcul automatique de la carrière complète
  - Le traitement des avancements
"""

import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sirh.db')

# Année administrative = 360 jours, mois = 30 jours
JOURS_PAR_AN = 360
JOURS_PAR_AVANCEMENT = 720  # 2 ans


def get_db(db_path=None):
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ajouter_jours(date_str, jours):
    """Ajouter un nombre de jours à une date (format YYYY-MM-DD)."""
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    return (dt + timedelta(days=jours)).strftime('%Y-%m-%d')


# ══════════════════════════════════════════════════════════════════════
# GRILLE DE PROGRESSION
# ══════════════════════════════════════════════════════════════════════

def get_progression_grille(db_path=None, statut=None, corps=None):
    """
    Récupérer la grille de progression ordonnée pour un corps.
    Retourne la liste des paliers dans l'ordre croissant du rang.
    """
    conn = get_db(db_path)
    rows = conn.execute(
        """SELECT * FROM progression_grille
           WHERE statut = ? AND corps = ?
           ORDER BY rang ASC""",
        (statut, corps)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_palier_par_rang(db_path=None, statut=None, corps=None, rang=None):
    """Récupérer un palier spécifique par son rang."""
    conn = get_db(db_path)
    row = conn.execute(
        """SELECT * FROM progression_grille
           WHERE statut = ? AND corps = ? AND rang = ?""",
        (statut, corps, rang)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ══════════════════════════════════════════════════════════════════════
# MISE EN SOLDE
# ══════════════════════════════════════════════════════════════════════

def mise_en_solde(db_path=None, agent_id=None, date_titularisation=None,
                  rang_initial=1, services_anterieurs=None):
    """
    Mettre un agent en solde : enregistrer sa titularisation,
    ses services antérieurs, et calculer toute sa carrière.

    services_anterieurs : liste de dicts
        [{'type_service': 'volontaire', 'date_debut': '2018-01-01',
          'date_fin': '2019-12-31', 'duree_jours': 720}, ...]

    Retourne la carrière complète calculée.
    """
    if not agent_id or not date_titularisation:
        return {'error': 'agent_id et date_titularisation requis'}

    conn = get_db(db_path)

    # Vérifier que l'agent existe
    agent = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    if not agent:
        conn.close()
        return {'error': 'Agent non trouvé'}

    # Récupérer la grille de progression
    grille = conn.execute(
        """SELECT * FROM progression_grille
           WHERE statut = ? AND corps = ?
           ORDER BY rang ASC""",
        (agent['statut'], agent['corps'])
    ).fetchall()

    if not grille:
        conn.close()
        return {'error': f"Pas de grille de progression pour {agent['statut']}/{agent['corps']}"}

    grille = [dict(g) for g in grille]

    # Trouver le palier initial
    palier_initial = None
    for g in grille:
        if g['rang'] == rang_initial:
            palier_initial = g
            break

    if not palier_initial:
        conn.close()
        return {'error': f'Rang initial {rang_initial} non trouvé dans la grille'}

    # ── Supprimer les données existantes ────────────────────────────
    conn.execute("DELETE FROM carriere_agent WHERE agent_id = ?", (agent_id,))
    conn.execute("DELETE FROM validations_service WHERE agent_id = ?", (agent_id,))
    conn.execute("DELETE FROM mise_en_solde WHERE agent_id = ?", (agent_id,))

    # ── Enregistrer la mise en solde ────────────────────────────────
    conn.execute(
        """INSERT INTO mise_en_solde
           (agent_id, date_titularisation, rang_initial, classe_initiale,
            echelon_initial, indice_initial)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (agent_id, date_titularisation, rang_initial,
         palier_initial['classe'], palier_initial['echelon'], palier_initial['indice'])
    )

    # ── Enregistrer les services antérieurs ─────────────────────────
    total_jours_validation = 0
    if services_anterieurs:
        for sa in services_anterieurs:
            duree = sa.get('duree_jours', 0)
            conn.execute(
                """INSERT INTO validations_service
                   (agent_id, type_service, date_debut, date_fin, duree_jours)
                   VALUES (?, ?, ?, ?, ?)""",
                (agent_id, sa['type_service'], sa['date_debut'],
                 sa['date_fin'], duree)
            )
            total_jours_validation += duree

    # ── Calculer la carrière complète ───────────────────────────────
    carriere = _calculer_carriere(
        grille, rang_initial, date_titularisation, total_jours_validation
    )

    # ── Enregistrer tous les paliers dans carriere_agent ────────────
    for etape in carriere:
        conn.execute(
            """INSERT INTO carriere_agent
               (agent_id, rang, classe, echelon, indice, date_effet,
                type_mouvement, reference_acte, traite, date_traitement)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (agent_id, etape['rang'], etape['classe'], etape['echelon'],
             etape['indice'], etape['date_effet'], etape['type_mouvement'],
             etape.get('reference_acte'), 0, None)
        )

    # ── Mettre à jour l'agent avec sa position actuelle ─────────────
    # (On met la position de titularisation, le traitement mettra à jour)
    conn.execute(
        """UPDATE agents SET
            grade = ?, echelon = ?, indice = ?
           WHERE id = ?""",
        (palier_initial['classe'], palier_initial['echelon'],
         palier_initial['indice'], agent_id)
    )

    conn.commit()
    conn.close()

    return {
        'agent_id': agent_id,
        'date_titularisation': date_titularisation,
        'rang_initial': rang_initial,
        'position_initiale': f"{palier_initial['classe']} {palier_initial['echelon']}e éch.",
        'jours_validation': total_jours_validation,
        'annees_validation': round(total_jours_validation / JOURS_PAR_AN, 1),
        'nb_etapes': len(carriere),
        'carriere': carriere,
    }


def _calculer_carriere(grille, rang_initial, date_titularisation, jours_validation):
    """
    Calculer toute la carrière d'un agent à partir de :
    - sa grille de progression ordonnée
    - son rang initial (position de titularisation)
    - sa date de titularisation
    - ses jours de validation (ancienneté antérieure)

    Retourne une liste d'étapes :
    [{rang, classe, echelon, indice, date_effet, type_mouvement}, ...]
    """
    carriere = []
    rang_courant = rang_initial
    jours_restants = jours_validation
    date_effet = date_titularisation

    # Indexer la grille par rang
    grille_map = {g['rang']: g for g in grille}
    rang_max = max(g['rang'] for g in grille)

    # ── Étape 0 : Position de titularisation ────────────────────────
    palier = grille_map.get(rang_courant)
    if not palier:
        return carriere

    carriere.append({
        'rang': rang_courant,
        'classe': palier['classe'],
        'echelon': palier['echelon'],
        'indice': palier['indice'],
        'date_effet': date_titularisation,
        'type_mouvement': 'titularisation',
    })

    # ── Phase 1 : Consommer la validation ───────────────────────────
    while jours_restants > 0 and rang_courant < rang_max:
        rang_suivant = rang_courant + 1
        palier_suivant = grille_map.get(rang_suivant)
        if not palier_suivant:
            break

        duree_avancement = palier['duree_jours']
        if duree_avancement <= 0:
            break  # Dernier palier, pas d'avancement possible

        if jours_restants >= duree_avancement:
            # Validation couvre entièrement cet avancement
            jours_restants -= duree_avancement
            rang_courant = rang_suivant
            palier = palier_suivant

            carriere.append({
                'rang': rang_courant,
                'classe': palier['classe'],
                'echelon': palier['echelon'],
                'indice': palier['indice'],
                'date_effet': date_titularisation,  # Même date !
                'type_mouvement': 'validation',
            })
        else:
            # Validation couvre partiellement
            jours_a_attendre = duree_avancement - jours_restants
            jours_restants = 0
            rang_courant = rang_suivant
            palier = palier_suivant

            date_effet = ajouter_jours(date_titularisation, jours_a_attendre)

            carriere.append({
                'rang': rang_courant,
                'classe': palier['classe'],
                'echelon': palier['echelon'],
                'indice': palier['indice'],
                'date_effet': date_effet,
                'type_mouvement': 'validation',
            })

    # ── Phase 2 : Avancements normaux après la validation ───────────
    while rang_courant < rang_max:
        duree_avancement = palier['duree_jours']
        if duree_avancement <= 0:
            break  # Dernier palier

        rang_suivant = rang_courant + 1
        palier_suivant = grille_map.get(rang_suivant)
        if not palier_suivant:
            break

        date_effet = ajouter_jours(date_effet, duree_avancement)
        rang_courant = rang_suivant
        palier = palier_suivant

        carriere.append({
            'rang': rang_courant,
            'classe': palier['classe'],
            'echelon': palier['echelon'],
            'indice': palier['indice'],
            'date_effet': date_effet,
            'type_mouvement': 'avancement',
        })

    return carriere


# ══════════════════════════════════════════════════════════════════════
# CONSULTATION CARRIÈRE
# ══════════════════════════════════════════════════════════════════════

def get_carriere_agent(db_path=None, agent_id=None):
    """
    Récupérer la carrière complète d'un agent avec toutes les étapes
    et l'état de traitement.
    """
    if not agent_id:
        return {'error': 'agent_id requis'}

    conn = get_db(db_path)

    # Agent
    agent = conn.execute("""
        SELECT a.*, s.nom as service_nom, m.nom as ministere_nom
        FROM agents a
        LEFT JOIN services s ON a.service_id = s.id
        LEFT JOIN directions d ON s.direction_id = d.id
        LEFT JOIN directions_generales dg ON d.direction_generale_id = dg.id
        LEFT JOIN ministeres m ON dg.ministere_id = m.id
        WHERE a.id = ?
    """, (agent_id,)).fetchone()

    if not agent:
        conn.close()
        return {'error': 'Agent non trouvé'}

    # Mise en solde
    mes = conn.execute(
        "SELECT * FROM mise_en_solde WHERE agent_id = ?", (agent_id,)
    ).fetchone()

    # Services antérieurs
    validations = conn.execute(
        "SELECT * FROM validations_service WHERE agent_id = ? ORDER BY date_debut",
        (agent_id,)
    ).fetchall()

    # Carrière
    etapes = conn.execute(
        """SELECT * FROM carriere_agent
           WHERE agent_id = ?
           ORDER BY rang ASC""",
        (agent_id,)
    ).fetchall()

    conn.close()

    if not mes:
        return {
            'agent': dict(agent),
            'mise_en_solde': None,
            'validations': [],
            'carriere': [],
            'message': 'Agent non mis en solde',
        }

    return {
        'agent': dict(agent),
        'mise_en_solde': dict(mes),
        'validations': [dict(v) for v in validations],
        'carriere': [dict(e) for e in etapes],
    }


def get_carriere_par_matricule(db_path=None, matricule=None):
    """Récupérer la carrière par matricule."""
    conn = get_db(db_path)
    agent = conn.execute(
        "SELECT id FROM agents WHERE matricule = ?", (matricule,)
    ).fetchone()
    conn.close()

    if not agent:
        return {'error': f'Matricule {matricule} non trouvé'}

    return get_carriere_agent(db_path, agent['id'])


# ══════════════════════════════════════════════════════════════════════
# TRAITEMENT D'UN AVANCEMENT
# ══════════════════════════════════════════════════════════════════════

def traiter_avancement(db_path=None, carriere_id=None, reference_acte=None):
    """
    Traiter un avancement : marquer comme traité avec la référence de l'acte.
    Met à jour la position de l'agent (grade, échelon, indice).

    Retourne l'étape traitée.
    """
    if not carriere_id:
        return {'error': 'carriere_id requis'}

    conn = get_db(db_path)

    # Récupérer l'étape
    etape = conn.execute(
        "SELECT * FROM carriere_agent WHERE id = ?", (carriere_id,)
    ).fetchone()

    if not etape:
        conn.close()
        return {'error': 'Étape de carrière non trouvée'}

    if etape['traite']:
        conn.close()
        return {'error': 'Cet avancement a déjà été traité'}

    # Vérifier que la date d'effet n'est pas dans le futur
    date_effet = datetime.strptime(etape['date_effet'], '%Y-%m-%d')
    aujourdhui = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if date_effet > aujourdhui:
        conn.close()
        return {'error': 'Impossible de traiter un avancement dont la date est postérieure à aujourd\'hui'}

    # Vérifier que les étapes précédentes sont traitées
    non_traites = conn.execute(
        """SELECT COUNT(*) as c FROM carriere_agent
           WHERE agent_id = ? AND rang < ? AND traite = 0""",
        (etape['agent_id'], etape['rang'])
    ).fetchone()['c']

    if non_traites > 0:
        conn.close()
        return {'error': 'Des avancements précédents n\'ont pas encore été traités'}

    # Marquer comme traité
    date_traitement = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute(
        """UPDATE carriere_agent
           SET traite = 1, reference_acte = ?, date_traitement = ?
           WHERE id = ?""",
        (reference_acte, date_traitement, carriere_id)
    )

    # Mettre à jour la position de l'agent
    conn.execute(
        """UPDATE agents
           SET grade = ?, echelon = ?, indice = ?
           WHERE id = ?""",
        (etape['classe'], etape['echelon'], etape['indice'], etape['agent_id'])
    )

    conn.commit()
    conn.close()

    return {
        'message': f"Avancement traité : {etape['classe']} {etape['echelon']}e éch.",
        'carriere_id': carriere_id,
        'reference_acte': reference_acte,
        'date_traitement': date_traitement,
    }


def traiter_batch_avancements(db_path=None, agent_id=None, traitements=None):
    """
    Traiter plusieurs avancements d'un coup.
    traitements : liste de dicts [{carriere_id, reference_acte}, ...]
    """
    if not traitements:
        return {'error': 'Aucun traitement fourni'}

    resultats = []
    erreurs = []

    for t in traitements:
        res = traiter_avancement(db_path, t.get('carriere_id'), t.get('reference_acte'))
        if 'error' in res:
            erreurs.append({**t, 'error': res['error']})
        else:
            resultats.append(res)

    return {
        'total_traites': len(resultats),
        'total_erreurs': len(erreurs),
        'resultats': resultats,
        'erreurs': erreurs,
    }


# ══════════════════════════════════════════════════════════════════════
# UTILITAIRES
# ══════════════════════════════════════════════════════════════════════

def get_corps_disponibles(db_path=None, statut=None):
    """Récupérer les corps disponibles pour un statut dans la grille de progression."""
    conn = get_db(db_path)
    rows = conn.execute(
        "SELECT DISTINCT corps FROM progression_grille WHERE statut = ? ORDER BY corps",
        (statut,)
    ).fetchall()
    conn.close()
    return [r['corps'] for r in rows]


def get_rangs_par_corps(db_path=None, statut=None, corps=None):
    """Récupérer tous les rangs pour un corps (pour le formulaire de mise en solde)."""
    conn = get_db(db_path)
    rows = conn.execute(
        """SELECT rang, classe, echelon, indice FROM progression_grille
           WHERE statut = ? AND corps = ?
           ORDER BY rang ASC""",
        (statut, corps)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == '__main__':
    # Test rapide
    print("=== Test du moteur d'avancement ===\n")

    # Simuler une mise en solde avec validation
    result = mise_en_solde(
        agent_id=1,
        date_titularisation='2023-01-01',
        rang_initial=1,
        services_anterieurs=[
            {'type_service': 'volontaire', 'date_debut': '2018-01-01',
             'date_fin': '2019-12-31', 'duree_jours': 720},
            {'type_service': 'contractuel', 'date_debut': '2020-01-01',
             'date_fin': '2022-12-31', 'duree_jours': 1080},
        ]
    )

    if 'error' in result:
        print(f"Erreur: {result['error']}")
    else:
        print(f"Agent mis en solde le {result['date_titularisation']}")
        print(f"Position initiale: {result['position_initiale']}")
        print(f"Validation: {result['annees_validation']} ans ({result['jours_validation']} jours)")
        print(f"\nCarrière calculée ({result['nb_etapes']} étapes):")
        for e in result['carriere']:
            print(f"  Rang {e['rang']:2d} | {e['classe']:20s} éch.{e['echelon']} | "
                  f"ind.{e['indice']:4d} | {e['date_effet']} | {e['type_mouvement']}")
