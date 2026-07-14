from tiff.trace_net_answer_quality_guard_v1 import *
def test_prefix():
 assert requested_prefix("The P/N starts with MS49")=="MS49"
 assert evaluate_answer_quality(query="The P/N starts with MS49",answer="Candidate: MS4956",trace={"route":"guided_discovery","follow_up_questions":[]})==[]
def test_noise():
 assert is_noise_candidate("48.321s")
 assert is_noise_candidate("4949276e-05")
 assert is_noise_candidate("n120-48024-001")
def test_bad_prefix():
 assert evaluate_answer_quality(query="The P/N starts with PE13",answer="Candidate: 1300077e-06",trace={"route":"guided_discovery","follow_up_questions":[]})
