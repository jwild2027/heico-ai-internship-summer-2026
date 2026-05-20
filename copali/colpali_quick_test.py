"""Quick import test for ColPali/Byaldi without downloading model weights."""

try:
    from colpali_engine.models import ColPali, ColPaliProcessor
    print("colpali_engine available: ColPali and ColPaliProcessor imported")
    print("ColPali doc:", ColPali.__doc__.splitlines()[0])
except Exception as e:
    print("colpali_engine import failed:", e)

try:
    from byaldi.colpali import ColPaliModel
    print("Byaldi available: ColPaliModel imported")
    print("ColPaliModel doc:", ColPaliModel.__doc__.splitlines()[0] if ColPaliModel.__doc__ else "<no doc>")
except Exception as e:
    print("byaldi import failed:", e)

print('\nDone.')
