import importlib

names = ['colpali_engine','colpali','byaldi','byaldi_engine','colpali.engine','colpali_engine.cli','byaldi.engine']

for n in names:
    try:
        m = importlib.import_module(n)
        print(f"IMPORT_OK:{n}:{getattr(m,'__file__',None)}")
    except Exception as e:
        print(f"IMPORT_FAIL:{n}:{e}")
