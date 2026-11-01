"""Simulation fidele des boucles Arduino : 3 appuis nets de 200 ms, espaces de
300 ms, boucle a 1 ms. On compare le compteur du FOURNISSEUR (anti-rebond
correct) aux compteurs des 3 reimplementations generees."""
HIGH, LOW = 1, 0

def sequence():
    """(temps_ms, etat_broche) -- INPUT_PULLUP : appuye = LOW."""
    t, out = 0, []
    for _ in range(3):
        for _ in range(300): out.append((t, HIGH)); t += 1   # relache
        for _ in range(200): out.append((t, LOW));  t += 1   # appui 200 ms
    for _ in range(300): out.append((t, HIGH)); t += 1
    return out

def fournisseur(seq):
    nb, dernierEtat, dernierChangement = 0, HIGH, 0
    for t, lecture in seq:
        if lecture != dernierEtat and t - dernierChangement > 50:
            dernierChangement = t; dernierEtat = lecture
            if lecture == LOW: nb += 1
    return nb

def run1(seq):
    pressCount, lastButtonState, lastDebounceTime = 0, HIGH, 0
    for t, reading in seq:
        if reading != lastButtonState and (t - lastDebounceTime) > 50:
            lastButtonState = reading; lastDebounceTime = t
        if reading == LOW and lastButtonState == HIGH:
            pressCount += 1
    return pressCount

def run3(seq):
    pressCount, lastButtonState, lastDebounceTime = 0, HIGH, 0
    for t, reading in seq:
        if reading != lastButtonState and (t - lastDebounceTime) > 50:
            lastButtonState = reading; lastDebounceTime = t
        if reading == LOW and lastButtonState == HIGH:
            pressCount += 1
        lastButtonState = reading          # affectation de fin de boucle
    return pressCount

def run4(seq):
    pressCount, lastButtonState, lastDebounceTime = 0, HIGH, 0
    allume = 0
    for t, reading in seq:
        if reading != lastButtonState and (t - lastDebounceTime) > 50:
            lastButtonState = reading; lastDebounceTime = t
        if reading == LOW and lastButtonState == HIGH:
            pressCount += 1
            if pressCount >= 3: allume += 1; pressCount = 0
        if reading == HIGH:
            pressCount = 0
    return pressCount, allume

seq = sequence()
attendu = fournisseur(seq)
print(f"FOURNISSEUR (anti-rebond correct) : {attendu} appuis comptes  <- la verite")
print(f"  reimplementation #1 : {run1(seq)}")
print(f"  reimplementation #3 : {run3(seq)}")
c4, a4 = run4(seq)
print(f"  reimplementation #4 : compteur={c4}, allumages LED={a4}")
print("\nLa LED doit s'allumer au 3e appui.")

# ── L'anti-rebond CANONIQUE que le modele ecrit quand la fonctionnalite est
# demandee d'UN SEUL TENANT (4/4 identiques). Compte-t-il juste ?
def canonique(seq, debounceDelay=50):
    pressCount = 0
    lastButtonState, buttonState, lastDebounceTime = HIGH, HIGH, 0
    for t, reading in seq:
        if reading != lastButtonState:
            lastDebounceTime = t
        if (t - lastDebounceTime) > debounceDelay:
            if reading != buttonState:
                buttonState = reading
                if buttonState == LOW:
                    if lastButtonState == HIGH:
                        pressCount += 1
        lastButtonState = reading
    return pressCount

print(f"\n  anti-rebond CANONIQUE (genere d'un seul tenant) : {canonique(seq)}")

# ── VALIDATION DE L'INSTRUMENT : l'anti-rebond Arduino AUTHENTIQUE (celui de
# l'exemple officiel Debounce.ino) doit compter 3. S'il compte 3, le
# simulateur est sain et les 0 ci-dessus sont bien des defauts du code.
def canonique_authentique(seq, debounceDelay=50):
    pressCount = 0
    lastButtonState, buttonState, lastDebounceTime = HIGH, HIGH, 0
    for t, reading in seq:
        if reading != lastButtonState:
            lastDebounceTime = t
        if (t - lastDebounceTime) > debounceDelay:
            if reading != buttonState:
                buttonState = reading
                if buttonState == LOW:
                    pressCount += 1        # <- SANS la condition en trop
        lastButtonState = reading
    return pressCount

print(f"  anti-rebond AUTHENTIQUE (Debounce.ino)          : {canonique_authentique(seq)}"
      "   <- valide l'instrument")
