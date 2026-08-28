"""Module wiring — generation de schemas de cablage adaptatifs.

Pipeline :
    EXTRACT (markers) -> INFER (inference) -> PLACE (layout/) -> ROUTE
    (routing/) -> RENDER (layout/renderer.py) -> PERSIST -> DISPLAY (dialog).

Le point d'entree principal pour le netlist est `wiring_pipeline.generate_wiring(code, board_id)`.
Le pipeline complet (netlist -> SVG + instructions) vit dans `layout/pipeline.py`.
"""
