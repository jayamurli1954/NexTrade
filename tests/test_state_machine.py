# tests/test_state_machine.py
"""
Unit Test Suite for NexTrade Execution State Machine (Sub-Phase 3D).
Tests valid transition paths and verifies that illegal state transition jumps raise ValueError.
"""
import unittest

from contracts.execution import ExecutionStatus
from execution.state_machine import ExecutionStateMachine, VALID_TRANSITIONS


class TestExecutionStateMachine(unittest.TestCase):

    def test_valid_execution_transition_flow(self):
        sm = ExecutionStateMachine(execution_request_id="EXREQ-SM-01")
        self.assertEqual(sm.current_status, ExecutionStatus.CREATED)
        self.assertFalse(sm.is_terminal)

        # CREATED -> AUTHORIZED
        sm.transition_to(ExecutionStatus.AUTHORIZED, reason="RISK_APPROVED")
        self.assertEqual(sm.current_status, ExecutionStatus.AUTHORIZED)

        # AUTHORIZED -> SUBMITTED
        sm.transition_to(ExecutionStatus.SUBMITTED, reason="SENT_TO_BROKER")
        self.assertEqual(sm.current_status, ExecutionStatus.SUBMITTED)

        # SUBMITTED -> PARTIALLY_FILLED
        sm.transition_to(ExecutionStatus.PARTIALLY_FILLED, reason="PARTIAL_FILL_RECEIVED")
        self.assertEqual(sm.current_status, ExecutionStatus.PARTIALLY_FILLED)
        self.assertFalse(sm.is_terminal)

        # PARTIALLY_FILLED -> FILLED
        sm.transition_to(ExecutionStatus.FILLED, reason="FINAL_FILL_RECEIVED")
        self.assertEqual(sm.current_status, ExecutionStatus.FILLED)
        self.assertTrue(sm.is_terminal)

    def test_illegal_transition_raises_value_error(self):
        sm = ExecutionStateMachine(execution_request_id="EXREQ-SM-02")
        
        # CREATED -> FILLED is illegal!
        with self.assertRaises(ValueError) as ctx:
            sm.transition_to(ExecutionStatus.FILLED, reason="ILLEGAL")
        self.assertIn("Illegal state transition", str(ctx.exception))

    def test_rejected_terminal_state_transition_fails(self):
        sm = ExecutionStateMachine(execution_request_id="EXREQ-SM-03")
        sm.transition_to(ExecutionStatus.AUTHORIZED)
        sm.transition_to(ExecutionStatus.REJECTED)
        self.assertTrue(sm.is_terminal)

        # REJECTED -> FILLED is illegal!
        with self.assertRaises(ValueError) as ctx:
            sm.transition_to(ExecutionStatus.FILLED)
        self.assertIn("Illegal state transition", str(ctx.exception))

    def test_submitted_to_unknown_transition(self):
        sm = ExecutionStateMachine(execution_request_id="EXREQ-SM-04")
        sm.transition_to(ExecutionStatus.AUTHORIZED)
        sm.transition_to(ExecutionStatus.SUBMITTED)
        sm.transition_to(ExecutionStatus.UNKNOWN, reason="SOCKET_TIMEOUT")
        self.assertEqual(sm.current_status, ExecutionStatus.UNKNOWN)
        self.assertTrue(sm.is_terminal)


if __name__ == "__main__":
    unittest.main()
