"""Regression for the actual native fixture continuation."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).absolute().parents[1]
spec=importlib.util.spec_from_file_location("native_fixture_probe",ROOT/"tests/check_codex_tool_discovery.py")
fixture=importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
WAIT={"type":"function","name":"wait","parameters":{"properties":{"cell_id":{"type":"string"}}}}

def body(ident,status,*chunks,tools=(WAIT,)):
    return {"tools":list(tools),"input":[{"type":"custom_tool_call_output" if ident=="portable-probe" else "function_call_output",
        "call_id":ident,"output":[{"type":"input_text","text":status+"\nWall time 31.0 seconds\nOutput:\n"},
        *({"type":"input_text","text":json.dumps(chunk)} for chunk in chunks)]}]}

class NativeFixtureContinuationTests(unittest.TestCase):
    def setUp(self):
        self.out=contextlib.redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__,None,None,None)

    def test_observed_yield_shape_waits_instead_of_requiring_final_marker(self):
        state=fixture.NativeProbeContinuation(True)
        first=body("portable-probe","Script running with cell ID 1",
                   {"chunk_id":"f61ea4","session_id":99056,"output":"NATIVE_RG16_SEARCH_AND_DISCOVERY=PASS\r\n"})
        self.assertNotIn(fixture.BROWSER_MARKER,json.dumps(first))
        follow=state.receive(first)
        self.assertEqual(follow["name"],"wait")
        self.assertEqual(json.loads(follow["arguments"])["cell_id"],"1")
        self.assertFalse(state.finished)
        again=state.receive(body(follow["call_id"],"Script running with cell ID 1"))
        self.assertEqual(state.wait_count,2)
        self.assertIsNone(state.receive(body(again["call_id"],"Script completed",
                         {"exit_code":0,"output":'{"title":"PORTABLE_TASK_RENDERED_0172"}\n'})))
        self.assertTrue(state.finished)
        self.assertEqual(state.shell_exit,0)
        self.assertIn(fixture.BROWSER_MARKER,"".join(state.evidence))

    def test_cell_completion_requires_real_successful_shell_exit(self):
        for status,chunks in (
            ("Script completed",({"session_id":99056,"output":fixture.BROWSER_MARKER},)),
            ("Script completed",({"exit_code":1,"output":fixture.BROWSER_MARKER},)),
            ("Script failed",({"exit_code":0,"output":fixture.BROWSER_MARKER},)),
            ("Script terminated",()),
        ):
            with self.subTest(status=status,chunks=chunks):
                state=fixture.NativeProbeContinuation(True)
                with self.assertRaises(AssertionError):state.receive(body("portable-probe",status,*chunks))
                self.assertFalse(state.finished)

    def test_wait_is_bound_to_exact_call_and_cell(self):
        state=fixture.NativeProbeContinuation(True)
        follow=state.receive(body("portable-probe","Script running with cell ID 1"))
        with self.assertRaises(AssertionError):
            state.receive(body("other-call","Script completed",{"exit_code":0,"output":fixture.BROWSER_MARKER}))
        with self.assertRaises(AssertionError):
            state.receive(body(follow["call_id"],"Script running with cell ID 2"))
        self.assertFalse(state.finished)
        with self.assertRaises(AssertionError):
            fixture.NativeProbeContinuation(True).receive(body("portable-probe","Script running with cell ID 1",tools=()))

    def test_direct_completed_output_retains_original_contract(self):
        state=fixture.NativeProbeContinuation(False)
        response={"input":[{"type":"function_call_output","call_id":"portable-probe",
                  "output":"Chunk ID: synthetic\nProcess exited with code 0\nOutput:\n"+fixture.TOOL_MARKER}]}
        self.assertIsNone(state.receive(response))
        self.assertTrue(state.finished)
        response["input"][0]["output"]=fixture.TOOL_MARKER
        with self.assertRaises(AssertionError):fixture.NativeProbeContinuation(False).receive(response)

if __name__=="__main__":
    unittest.main()
