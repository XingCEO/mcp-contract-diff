import unittest
from mcp_contract_diff import analyze

class CompatibilityTests(unittest.TestCase):
    def run_diff(self, old, new, output=False):
        key = 'outputSchema' if output else 'inputSchema'
        return analyze({'before':{'tools':[{'name':'x',key:old}]},'after':{'tools':[{'name':'x',key:new}]}})
    def test_optional_addition_is_safe(self):
        self.assertEqual(self.run_diff({'type':'object'},{'type':'object','properties':{'x':{'type':'string'}}})['breaking'],0)
    def test_nested_requirement(self):
        r=self.run_diff({'properties':{'x':{}}},{'properties':{'x':{'required':['y']}}})
        self.assertEqual(r['findings'][0]['path'],'/inputSchema/properties/x/required')
    def test_input_enum_narrowing(self):
        self.assertEqual(self.run_diff({'enum':['a','b']},{'enum':['a']})['breaking'],1)
    def test_output_enum_widening(self):
        self.assertEqual(self.run_diff({'enum':['a']},{'enum':['a','b']},True)['breaking'],1)
    def test_unknown_constraint_review(self):
        self.assertEqual(self.run_diff({'minimum':0},{'minimum':2})['findings'][0]['severity'],'review')
    def test_duplicate_names(self):
        with self.assertRaises(ValueError):
            analyze({'before':{'tools':[{'name':'x'},{'name':'x'}]},'after':{'tools':[]}})
