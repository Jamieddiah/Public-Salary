"""
SIRH — Moteur de Calcul de Paie
Administration Publique Sénégalaise

Gère 3 régimes :
  - Titulaires / Contractuels (IPRES standard)
  - Militaires / Gendarmerie / Police (FCRPS)
"""

import sqlite3
import os
import math
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sirh.db')


def get_db(db_path=None):
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ══════════════════════════════════════════════════════════════════════
# VALEUR DU POINT
# ══════════════════════════════════════════════════════════════════════

def get_valeur_point(db_path=None, periode='2026-03'):
    """Récupérer la valeur du point d'indice pour une période donnée."""
    conn = get_db(db_path)
    row = conn.execute(
        "SELECT valeur FROM parametres_paie WHERE code='VALEUR_POINT' AND periode=? AND actif=1",
        (periode,)
    ).fetchone()
    conn.close()
    return row['valeur'] if row else 475.0


# ══════════════════════════════════════════════════════════════════════
# PRIMES STATUTAIRES
# ══════════════════════════════════════════════════════════════════════

def calculer_primes_statutaires(db_path=None, agent=None):
    """
    Calculer toutes les primes applicables à un agent.
    agent : dict avec clés statut, corps, salaire_base
    Retourne : liste de dicts {code, libelle, montant, imposable}
    """
    if not agent:
        return []

    conn = get_db(db_path)
    primes_db = conn.execute(
        "SELECT * FROM primes_statutaires WHERE statut = ?",
        (agent['statut'],)
    ).fetchall()
    conn.close()

    result = []
    salaire_base = agent.get('salaire_base', 0)

    for p in primes_db:
        # Vérifier si un corps spécifique est requis
        if p['corps_requis'] and p['corps_requis'] != agent.get('corps'):
            continue

        if p['mode_calcul'] == 'fixe':
            montant = p['taux_ou_montant']
        else:  # pourcentage
            montant = salaire_base * p['taux_ou_montant'] / 100.0

        result.append({
            'code': p['code'],
            'libelle': p['libelle'],
            'montant': round(montant),
            'imposable': bool(p['imposable']),
        })

    return result


# ══════════════════════════════════════════════════════════════════════
# ÉLÉMENTS VARIABLES DE SALAIRE
# ══════════════════════════════════════════════════════════════════════

def get_evs_valides(db_path=None, agent_id=None, periode='2026-03', salaire_base=0):
    """
    Récupérer les EVS validés ou visés pour un agent et une période.
    Calcule le montant réel en fonction du type.
    """
    if not agent_id:
        return []

    conn = get_db(db_path)
    rows = conn.execute("""
        SELECT ev.*, te.code as type_code, te.libelle as type_libelle,
               te.type_evs, te.mode_calcul as type_mode, te.imposable as type_imposable,
               te.plafond
        FROM elements_variables ev
        JOIN types_evs te ON ev.type_evs_id = te.id
        WHERE ev.agent_id = ? AND ev.periode = ?
          AND ev.statut_validation IN ('valide', 'visa')
    """, (agent_id, periode)).fetchall()
    conn.close()

    result = []
    taux_horaire = salaire_base / 173.33 if salaire_base > 0 else 0
    taux_journalier = salaire_base / 30.0 if salaire_base > 0 else 0

    for r in rows:
        code = r['type_code']
        quantite = r['quantite'] or 0
        montant_saisi = r['montant'] or 0

        if code == 'HS_25':
            montant = quantite * taux_horaire * 1.25
        elif code == 'HS_50':
            montant = quantite * taux_horaire * 1.50
        elif code == 'MISSION_I':
            montant = quantite * 25000
        elif code == 'MISSION_E':
            montant = quantite * 75000
        elif code == 'PRIME_REND':
            montant = min(montant_saisi, 200000)
        elif code == 'ABS_INJ':
            montant = quantite * taux_journalier
        elif code in ('PRET_IPRES', 'PRET_BANQ'):
            montant = montant_saisi
        else:
            montant = montant_saisi

        result.append({
            'code': code,
            'libelle': r['type_libelle'],
            'type_evs': r['type_evs'],
            'quantite': quantite,
            'montant': round(montant),
            'imposable': bool(r['type_imposable']),
        })

    return result


# ══════════════════════════════════════════════════════════════════════
# PARTS FISCALES
# ══════════════════════════════════════════════════════════════════════

def calculer_parts_fiscales(situation_matrimoniale, nb_enfants):
    """
    Calculer le nombre de parts fiscales.
    - Célibataire / Divorcé(e) / Veuf(ve) : 1 part
    - Marié(e) : 1,5 parts
    - +0,5 par enfant à charge
    - Maximum 5 parts
    """
    if situation_matrimoniale == 'Marié(e)':
        parts = 1.5
    else:
        parts = 1.0
    parts += nb_enfants * 0.5
    return min(parts, 5.0)


# ══════════════════════════════════════════════════════════════════════
# IMPÔT SUR LE REVENU (IR)
# ══════════════════════════════════════════════════════════════════════

def calculer_ir_annuel(revenu_imposable_annuel, parts):
    """
    Calcul de l'IR selon le barème progressif sénégalais.
    1. Abattement forfaitaire : 30% plafonné à 900 000 FCFA/an
    2. Division par le nombre de parts
    3. Application du barème progressif
    4. Multiplication par le nombre de parts
    """
    if revenu_imposable_annuel <= 0:
        return 0

    # Étape 1 : Abattement forfaitaire de 30%, plafonné à 900 000
    abattement = min(revenu_imposable_annuel * 0.30, 900000)
    revenu_net = revenu_imposable_annuel - abattement

    if revenu_net <= 0:
        return 0

    # Étape 2 : Division par le nombre de parts
    revenu_par_part = revenu_net / parts

    # Étape 3 : Barème progressif
    tranches = [
        (630000,   0.00),
        (870000,   0.20),   # 1 500 000 - 630 000
        (2500000,  0.30),   # 4 000 000 - 1 500 000
        (4000000,  0.35),   # 8 000 000 - 4 000 000
        (float('inf'), 0.37),
    ]

    ir_par_part = 0
    reste = revenu_par_part
    for tranche_montant, taux in tranches:
        if reste <= 0:
            break
        imposable = min(reste, tranche_montant)
        ir_par_part += imposable * taux
        reste -= imposable

    # Étape 4 : Multiplication par le nombre de parts
    ir_total = ir_par_part * parts

    return max(round(ir_total), 0)


# ══════════════════════════════════════════════════════════════════════
# TRIMF (Taxe Représentative de l'Impôt Minimum Forfaitaire)
# ══════════════════════════════════════════════════════════════════════

def calculer_trimf_annuel(revenu_imposable_annuel):
    """
    Barème annuel TRIMF.
    """
    if revenu_imposable_annuel <= 0:
        return 0

    if revenu_imposable_annuel <= 630000:
        return 900
    elif revenu_imposable_annuel <= 1500000:
        return 3600
    elif revenu_imposable_annuel <= 4000000:
        return 4800
    elif revenu_imposable_annuel <= 8000000:
        return 7200
    else:
        return 9600


# ══════════════════════════════════════════════════════════════════════
# COTISATIONS SOCIALES
# ══════════════════════════════════════════════════════════════════════

def calculer_cotisations(brut_imposable, statut):
    """
    Calculer les cotisations employé et employeur.

    Régime standard (titulaire/contractuel) :
      - IPRES RG : 5,6% employé / 8,4% employeur (plafond 432 000)
      - IPRES RC : 2,4% employé / 3,6% employeur (tranche 432k-1 296k)
      - CSS AF   : 7% employeur (plafond 63 000)
      - CSS AT   : 3% employeur (plafond 63 000)
      - CFCE     : 3% employeur sur brut total

    Régime FCRPS (militaire/gendarmerie/police) :
      - FCRPS    : 4% employé / 6% employeur (pas de plafond simplifié)
      - Pas de Régime Cadre
      - CSS AF/AT et CFCE identiques
    """
    cotisations = {
        'ipres_rg_emp': 0,
        'ipres_rc_emp': 0,
        'ipres_rg_patron': 0,
        'ipres_rc_patron': 0,
        'css_af': 0,
        'css_at': 0,
        'cfce': 0,
    }

    if brut_imposable <= 0:
        return cotisations

    is_force = statut in ('militaire', 'gendarmerie', 'police')

    if is_force:
        # Régime FCRPS
        cotisations['ipres_rg_emp'] = round(brut_imposable * 0.04)
        cotisations['ipres_rg_patron'] = round(brut_imposable * 0.06)
        # Pas de Régime Cadre pour les forces
        cotisations['ipres_rc_emp'] = 0
        cotisations['ipres_rc_patron'] = 0
    else:
        # Régime IPRES standard
        base_rg = min(brut_imposable, 432000)
        cotisations['ipres_rg_emp'] = round(base_rg * 0.056)
        cotisations['ipres_rg_patron'] = round(base_rg * 0.084)

        # Régime Cadre (tranche supérieure)
        if brut_imposable > 432000:
            base_rc = min(brut_imposable, 1296000) - 432000
            cotisations['ipres_rc_emp'] = round(base_rc * 0.024)
            cotisations['ipres_rc_patron'] = round(base_rc * 0.036)

    # Cotisations patronales communes
    base_css = min(brut_imposable, 63000)
    cotisations['css_af'] = round(base_css * 0.07)
    cotisations['css_at'] = round(base_css * 0.03)
    cotisations['cfce'] = round(brut_imposable * 0.03)

    return cotisations


# ══════════════════════════════════════════════════════════════════════
# CALCUL COMPLET D'UN BULLETIN
# ══════════════════════════════════════════════════════════════════════

def calculer_bulletin(db_path=None, agent_id=None, periode='2026-03'):
    """
    Calculer le bulletin de paie complet pour un agent et une période.
    Enregistre le bulletin et ses lignes dans la base de données.
    Retourne le dict complet du bulletin.
    """
    if not agent_id:
        return {'error': 'agent_id requis'}

    conn = get_db(db_path)

    # 1. Récupérer l'agent
    agent_row = conn.execute("""
        SELECT a.*, s.nom as service_nom, s.direction_id,
               d.nom as direction_nom, d.direction_generale_id,
               dg.nom as dg_nom, dg.ministere_id,
               m.nom as ministere_nom
        FROM agents a
        LEFT JOIN services s ON a.service_id = s.id
        LEFT JOIN directions d ON s.direction_id = d.id
        LEFT JOIN directions_generales dg ON d.direction_generale_id = dg.id
        LEFT JOIN ministeres m ON dg.ministere_id = m.id
        WHERE a.id = ?
    """, (agent_id,)).fetchone()

    if not agent_row:
        conn.close()
        return {'error': 'Agent non trouvé'}

    agent = dict(agent_row)
    conn.close()

    # 2. Valeur du point
    valeur_point = get_valeur_point(db_path, periode)

    # 3. Salaire de base
    salaire_base = round(agent['indice'] * valeur_point)
    agent['salaire_base'] = salaire_base

    # 4. Primes statutaires
    primes = calculer_primes_statutaires(db_path, agent)
    primes_imposables = sum(p['montant'] for p in primes if p['imposable'])
    primes_non_imposables = sum(p['montant'] for p in primes if not p['imposable'])
    total_primes = primes_imposables + primes_non_imposables

    # 5. Éléments variables
    evs = get_evs_valides(db_path, agent_id, periode, salaire_base)
    evs_gains_imposables = sum(e['montant'] for e in evs if e['type_evs'] == 'gain' and e['imposable'])
    evs_gains_non_imposables = sum(e['montant'] for e in evs if e['type_evs'] == 'gain' and not e['imposable'])
    evs_retenues = sum(e['montant'] for e in evs if e['type_evs'] == 'retenue')
    total_evs_gains = evs_gains_imposables + evs_gains_non_imposables

    # 6. Brut imposable vs non imposable
    brut_imposable = salaire_base + primes_imposables + evs_gains_imposables
    brut_non_imposable = primes_non_imposables + evs_gains_non_imposables

    # 7. Cotisations sociales
    cotisations = calculer_cotisations(brut_imposable, agent['statut'])

    # 8. IR mensuel
    brut_imposable_annuel = brut_imposable * 12
    parts = calculer_parts_fiscales(agent['situation_matrimoniale'], agent['nb_enfants'])
    ir_annuel = calculer_ir_annuel(brut_imposable_annuel, parts)
    ir_mensuel = round(ir_annuel / 12)

    # 9. TRIMF mensuel
    trimf_annuel = calculer_trimf_annuel(brut_imposable_annuel)
    trimf_mensuel = round(trimf_annuel / 12)

    # 10. Total retenues employé
    total_retenues_employe = (
        cotisations['ipres_rg_emp'] +
        cotisations['ipres_rc_emp'] +
        ir_mensuel +
        trimf_mensuel +
        evs_retenues
    )

    # 11. Salaire net
    salaire_net = brut_imposable - cotisations['ipres_rg_emp'] - cotisations['ipres_rc_emp'] - ir_mensuel - trimf_mensuel + brut_non_imposable - evs_retenues

    # 12. Charges patronales
    total_charges_patronales = (
        cotisations['ipres_rg_patron'] +
        cotisations['ipres_rc_patron'] +
        cotisations['css_af'] +
        cotisations['css_at'] +
        cotisations['cfce']
    )

    # 13. Coût employeur
    cout_employeur = salaire_net + total_retenues_employe + total_charges_patronales

    # ── Enregistrer le bulletin ─────────────────────────────────────
    conn = get_db(db_path)
    cur = conn.cursor()

    # Supprimer un éventuel ancien bulletin pour cette période
    cur.execute("DELETE FROM lignes_bulletin WHERE bulletin_id IN (SELECT id FROM bulletins WHERE agent_id=? AND periode=?)", (agent_id, periode))
    cur.execute("DELETE FROM bulletins WHERE agent_id=? AND periode=?", (agent_id, periode))

    cur.execute("""
        INSERT INTO bulletins (
            agent_id, periode, salaire_base, total_primes,
            total_evs_gains, total_evs_retenues,
            salaire_brut_imposable, salaire_brut_non_imposable,
            ipres_rg_emp, ipres_rc_emp, ir_mensuel, trimf,
            total_retenues, salaire_net,
            charges_patronales_ipres_rg, charges_patronales_ipres_rc,
            charges_patronales_css_af, charges_patronales_css_at,
            charges_patronales_cfce, total_charges_patronales,
            cout_employeur
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        agent_id, periode, salaire_base, total_primes,
        total_evs_gains, evs_retenues,
        brut_imposable, brut_non_imposable,
        cotisations['ipres_rg_emp'], cotisations['ipres_rc_emp'],
        ir_mensuel, trimf_mensuel,
        total_retenues_employe, salaire_net,
        cotisations['ipres_rg_patron'], cotisations['ipres_rc_patron'],
        cotisations['css_af'], cotisations['css_at'],
        cotisations['cfce'], total_charges_patronales,
        cout_employeur
    ))

    bulletin_id = cur.lastrowid

    # ── Lignes de bulletin ──────────────────────────────────────────
    lignes = []

    # Salaire de base
    lignes.append(('SAL_BASE', 'Salaire de base', agent['indice'], valeur_point, salaire_base, 0))

    # Primes
    for p in primes:
        lignes.append((p['code'], p['libelle'], salaire_base if 'pourcentage' in str(p.get('mode', '')) else 0, 0, p['montant'], 0))

    # EVS gains
    for e in evs:
        if e['type_evs'] == 'gain':
            lignes.append((e['code'], e['libelle'], e.get('quantite', 0), 0, e['montant'], 0))

    # Retenues
    if cotisations['ipres_rg_emp'] > 0:
        is_force = agent['statut'] in ('militaire', 'gendarmerie', 'police')
        taux_rg = 4.0 if is_force else 5.6
        label_rg = 'FCRPS Régime Général' if is_force else 'IPRES Régime Général'
        lignes.append(('IPRES_RG', label_rg, brut_imposable, taux_rg, 0, cotisations['ipres_rg_emp']))

    if cotisations['ipres_rc_emp'] > 0:
        lignes.append(('IPRES_RC', 'IPRES Régime Cadre', brut_imposable, 2.4, 0, cotisations['ipres_rc_emp']))

    if ir_mensuel > 0:
        lignes.append(('IR', 'Impôt sur le Revenu', brut_imposable_annuel, 0, 0, ir_mensuel))

    if trimf_mensuel > 0:
        lignes.append(('TRIMF', 'TRIMF', 0, 0, 0, trimf_mensuel))

    # EVS retenues
    for e in evs:
        if e['type_evs'] == 'retenue':
            lignes.append((e['code'], e['libelle'], e.get('quantite', 0), 0, 0, e['montant']))

    for l in lignes:
        cur.execute("""
            INSERT INTO lignes_bulletin (bulletin_id, rubrique_code, rubrique_libelle, base, taux, montant_gain, montant_retenue)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (bulletin_id, *l))

    conn.commit()
    conn.close()

    # ── Résultat ────────────────────────────────────────────────────
    return {
        'bulletin_id': bulletin_id,
        'agent': {
            'id': agent['id'],
            'matricule': agent['matricule'],
            'nom': agent['nom'],
            'prenom': agent['prenom'],
            'statut': agent['statut'],
            'corps': agent['corps'],
            'grade': agent['grade'],
            'echelon': agent['echelon'],
            'indice': agent['indice'],
            'situation_matrimoniale': agent['situation_matrimoniale'],
            'nb_enfants': agent['nb_enfants'],
            'parts_fiscales': parts,
            'service': agent.get('service_nom', ''),
            'direction': agent.get('direction_nom', ''),
            'ministere': agent.get('ministere_nom', ''),
        },
        'periode': periode,
        'valeur_point': valeur_point,
        'salaire_base': salaire_base,
        'primes': primes,
        'total_primes': total_primes,
        'evs': evs,
        'total_evs_gains': total_evs_gains,
        'total_evs_retenues': evs_retenues,
        'brut_imposable': brut_imposable,
        'brut_non_imposable': brut_non_imposable,
        'cotisations': {
            'ipres_rg_emp': cotisations['ipres_rg_emp'],
            'ipres_rc_emp': cotisations['ipres_rc_emp'],
            'ir_mensuel': ir_mensuel,
            'trimf': trimf_mensuel,
        },
        'total_retenues': total_retenues_employe,
        'salaire_net': salaire_net,
        'charges_patronales': {
            'ipres_rg': cotisations['ipres_rg_patron'],
            'ipres_rc': cotisations['ipres_rc_patron'],
            'css_af': cotisations['css_af'],
            'css_at': cotisations['css_at'],
            'cfce': cotisations['cfce'],
        },
        'total_charges_patronales': total_charges_patronales,
        'cout_employeur': cout_employeur,
        'lignes': [{'code': l[0], 'libelle': l[1], 'base': l[2], 'taux': l[3], 'gain': l[4], 'retenue': l[5]} for l in lignes],
    }


# ══════════════════════════════════════════════════════════════════════
# CALCUL BATCH
# ══════════════════════════════════════════════════════════════════════

def calculer_batch(db_path=None, periode='2026-03'):
    """Calculer les bulletins pour tous les agents actifs."""
    conn = get_db(db_path)
    agents = conn.execute("SELECT id FROM agents WHERE actif = 1").fetchall()
    conn.close()

    resultats = []
    erreurs = []

    for a in agents:
        try:
            bulletin = calculer_bulletin(db_path, a['id'], periode)
            if 'error' in bulletin:
                erreurs.append({'agent_id': a['id'], 'error': bulletin['error']})
            else:
                resultats.append({
                    'agent_id': a['id'],
                    'matricule': bulletin['agent']['matricule'],
                    'nom': f"{bulletin['agent']['nom']} {bulletin['agent']['prenom']}",
                    'salaire_net': bulletin['salaire_net'],
                    'cout_employeur': bulletin['cout_employeur'],
                })
        except Exception as e:
            erreurs.append({'agent_id': a['id'], 'error': str(e)})

    return {
        'periode': periode,
        'total_calcules': len(resultats),
        'total_erreurs': len(erreurs),
        'resultats': resultats,
        'erreurs': erreurs,
        'masse_salariale_nette': sum(r['salaire_net'] for r in resultats),
        'cout_total_employeur': sum(r['cout_employeur'] for r in resultats),
    }


# ══════════════════════════════════════════════════════════════════════
# RAPPORT MASSE SALARIALE
# ══════════════════════════════════════════════════════════════════════

def rapport_masse_salariale(db_path=None, periode='2026-03', niveau='ministere'):
    """
    Générer un rapport de masse salariale agrégé.
    niveau : 'ministere' ou 'direction'
    """
    conn = get_db(db_path)

    if niveau == 'direction':
        query = """
            SELECT d.nom as entite, d.code,
                   COUNT(b.id) as nb_agents,
                   COALESCE(SUM(b.salaire_base), 0) as total_base,
                   COALESCE(SUM(b.total_primes), 0) as total_primes,
                   COALESCE(SUM(b.salaire_brut_imposable + b.salaire_brut_non_imposable), 0) as total_brut,
                   COALESCE(SUM(b.salaire_net), 0) as total_net,
                   COALESCE(SUM(b.total_charges_patronales), 0) as total_charges,
                   COALESCE(SUM(b.cout_employeur), 0) as total_cout
            FROM bulletins b
            JOIN agents a ON b.agent_id = a.id
            JOIN services s ON a.service_id = s.id
            JOIN directions d ON s.direction_id = d.id
            WHERE b.periode = ?
            GROUP BY d.id, d.nom, d.code
            ORDER BY d.nom
        """
    else:
        query = """
            SELECT m.nom as entite, m.code,
                   COUNT(b.id) as nb_agents,
                   COALESCE(SUM(b.salaire_base), 0) as total_base,
                   COALESCE(SUM(b.total_primes), 0) as total_primes,
                   COALESCE(SUM(b.salaire_brut_imposable + b.salaire_brut_non_imposable), 0) as total_brut,
                   COALESCE(SUM(b.salaire_net), 0) as total_net,
                   COALESCE(SUM(b.total_charges_patronales), 0) as total_charges,
                   COALESCE(SUM(b.cout_employeur), 0) as total_cout
            FROM bulletins b
            JOIN agents a ON b.agent_id = a.id
            JOIN services s ON a.service_id = s.id
            JOIN directions d ON s.direction_id = d.id
            JOIN directions_generales dg ON d.direction_generale_id = dg.id
            JOIN ministeres m ON dg.ministere_id = m.id
            WHERE b.periode = ?
            GROUP BY m.id, m.nom, m.code
            ORDER BY m.nom
        """

    rows = conn.execute(query, (periode,)).fetchall()
    conn.close()

    rapport = []
    totaux = {
        'nb_agents': 0, 'total_base': 0, 'total_primes': 0,
        'total_brut': 0, 'total_net': 0, 'total_charges': 0, 'total_cout': 0
    }

    for r in rows:
        entry = dict(r)
        rapport.append(entry)
        for k in totaux:
            totaux[k] += entry[k]

    return {
        'periode': periode,
        'niveau': niveau,
        'lignes': rapport,
        'totaux': totaux,
    }


if __name__ == '__main__':
    # Test rapide
    print("Test du moteur de paie...")
    vp = get_valeur_point()
    print(f"Valeur du point : {vp} FCFA")

    bulletin = calculer_bulletin(agent_id=1, periode='2026-03')
    if 'error' not in bulletin:
        print(f"Agent : {bulletin['agent']['nom']} {bulletin['agent']['prenom']}")
        print(f"Salaire base : {bulletin['salaire_base']:,} FCFA")
        print(f"Salaire net  : {bulletin['salaire_net']:,} FCFA")
        print(f"Coût employeur: {bulletin['cout_employeur']:,} FCFA")
    else:
        print(f"Erreur : {bulletin['error']}")
