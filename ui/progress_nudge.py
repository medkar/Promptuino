"""Logique PURE des nudges de progression de mode (aucun import Qt).

Un « nudge » pousse l'utilisateur vers le mode supérieur. Les compteurs et le
drapeau « vu » sont app-wide (persistés dans session.json par l'appelant) ;
ce module ne fait QUE décider s'il faut l'afficher maintenant.
"""
from __future__ import annotations

# Seuils (cf. décision produit : 5 / 15 / 5).
BEGINNER_GEN_THRESHOLD = 5
# Bandeau Intermédiaire→Avancé : compte les ACTIONS (Ajouter + Modifier +
# Régénérer + chaque segment d'édition manuelle). Relevé de 10 à 15 quand la
# régénération et l'édition manuelle sont entrées dans le décompte.
INTERMEDIATE_EDIT_THRESHOLD = 15
# Popup « 2 fenêtres » : après N segments d'édition manuelle en Intermédiaire.
MANUAL_EDIT_NUDGE_THRESHOLD = 5

# Clés de compteur (persistées app-wide).
COUNTER_BEGINNER = "beginner_gen"          # générations réussies en mode débutant
# Actions Intermédiaire : Ajouter/Modifier/Régénérer + segments d'édition manuelle.
COUNTER_INTERMEDIATE = "intermediate_edit"
# Segments d'édition manuelle SEULS (déclenche la popup 2 fenêtres).
COUNTER_MANUAL_EDIT = "intermediate_manual_edit"

# Clés de drapeau « nudge déjà montré » (persistées app-wide).
NUDGE_BEGINNER = "beginner_to_intermediate"
NUDGE_INTERMEDIATE = "intermediate_to_advanced"
NUDGE_MANUAL_EDIT = "manual_edit_to_advanced"


def should_show_nudge(*, count: int, threshold: int, seen: bool,
                      in_target_mode: bool) -> bool:
    """True ssi : on est encore dans le mode concerné, le nudge n'a jamais été
    montré, et le compteur a atteint le seuil."""
    return in_target_mode and (not seen) and count >= threshold


# ─── Nudge RÉPÉTÉ (popup « 2 fenêtres », QA C5 2026-08-08) ───────────────────
#
# Un nudge de PROGRESSION qui ne parle qu'une fois puis se tait pour toujours
# rate sa cible : mesuré sur une vraie session, le compteur d'éditions
# manuelles était à 119 sans qu'on ait jamais reparlé du mode Avancé.
# Il réapparaît donc à seuils croissants, puis se tait définitivement — assez
# pour insister, pas assez pour saouler (décision utilisateur : 5, 20, 40, 60).
MANUAL_EDIT_NUDGE_THRESHOLDS = (5, 20, 40, 60)


def next_threshold(thresholds, shown: int) -> int | None:
    """Compteur auquel le (shown+1)-ième affichage est dû, ou None une fois la
    série épuisée."""
    return thresholds[shown] if 0 <= shown < len(thresholds) else None


def should_show_repeating_nudge(*, count: int, thresholds, shown: int,
                                in_target_mode: bool) -> bool:
    """True ssi on est dans le mode concerné, la série n'est pas épuisée, et le
    compteur a atteint le seuil du prochain affichage."""
    t = next_threshold(thresholds, shown)
    return in_target_mode and t is not None and count >= t


def showings_so_far(*, shown: int | None, legacy_seen: bool, count: int,
                    thresholds) -> int:
    """Nombre d'affichages déjà faits, sessions d'avant le compteur comprises.

    `shown` vaut None quand la session a été écrite avant que ce compteur
    existe. On le RECONSTRUIT depuis le nombre de seuils que le compteur a déjà
    dépassés, au lieu de repartir de zéro : sinon un utilisateur de longue date
    (compteur à 119, tous les seuils franchis) verrait la série entière se
    déclencher d'un coup à la première occasion — l'inverse exact de ce que
    « ne pas saouler » demande.
    """
    if shown is not None:
        return shown
    if not legacy_seen:
        return 0
    return sum(1 for t in thresholds if count >= t)
