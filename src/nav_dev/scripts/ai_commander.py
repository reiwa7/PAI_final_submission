#!/usr/bin/env python3
"""Local LLM inference -> validated motion plan -> ROS 2 Twist.

Simulator demo only. No perception, obstacle avoidance, or position feedback.
New code for the final assignment; no cloud API or extra Python package needed.
"""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import time
from urllib.request import Request, ProxyHandler, build_opener

MOTIONS = {
    'forward': (0.15, 0.0), 'backward': (-0.15, 0.0),
    'left': (0.0, 0.50), 'right': (0.0, -0.50),
    'wait': (0.0, 0.0),
}
SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['steps'], 'properties': {'steps': {
        'type': 'array', 'minItems': 1, 'maxItems': 6,
        'items': {'type': 'object', 'additionalProperties': False,
                  'required': ['action', 'seconds'], 'properties': {
                      'action': {'type': 'string', 'enum': list(MOTIONS)},
                      'seconds': {'type': 'number', 'minimum': 0.5,
                                  'maximum': 4.0}}}}},
}
SYSTEM = """Convert the user's Japanese instruction into a motion plan.
Return ONLY a JSON object matching the supplied schema. Preserve action order.
forward=前進, backward=後退/バック, left=左旋回, right=右旋回,
wait=停止して待つ. Do not add actions the user did not request.
Use at most 6 steps, each 0.5 to 4 seconds; total at most 20 seconds.
If duration is unspecified, use 2 seconds. Short means 1 second.
For 'stop at the end', use wait for 1 second. Movement is relative to
the robot's CURRENT heading; do not invent global coordinates.
Impossible requests (vision, objects, destinations) must produce only
one wait step. This robot has NO camera, map, or obstacle avoidance.
Never output Python, shell, velocity values, or explanations."""


def validate_plan(plan):
    if not isinstance(plan, dict) or set(plan) != {'steps'}:
        raise ValueError('Plan must contain only steps')
    steps = plan['steps']
    if not isinstance(steps, list) or not 1 <= len(steps) <= 6:
        raise ValueError('Expected 1 to 6 steps')
    total = 0.0
    for s in steps:
        if not isinstance(s, dict) or set(s) != {'action', 'seconds'}:
            raise ValueError('Each step needs action and seconds only')
        if not isinstance(s['action'], str) or s['action'] not in MOTIONS:
            raise ValueError('Unknown action')
        v = s['seconds']
        if type(v) not in (int, float) or not math.isfinite(v):
            raise ValueError('Invalid seconds')
        if not 0.5 <= v <= 4.0:
            raise ValueError('seconds must be 0.5 to 4')
        total += v
    if total > 20.0:
        raise ValueError('Total duration exceeds 20 seconds')
    return plan


def infer(instruction, endpoint, model, timeout):
    body = {'model': model, 'system': SYSTEM, 'prompt': instruction,
            'format': SCHEMA, 'stream': False, 'keep_alive': '10m',
            'options': {'temperature': 0, 'seed': 42,
                        'num_ctx': 2048, 'num_predict': 256}}
    req = Request(endpoint.rstrip('/') + '/api/generate',
                  data=json.dumps(body).encode(),
                  headers={'Content-Type': 'application/json'})
    # Direct Docker network access, independent of proxy env variables.
    with build_opener(ProxyHandler({})).open(req, timeout=timeout) as response:
        raw = json.load(response)
    if raw.get('done') is not True or raw.get('done_reason') == 'length':
        raise ValueError('Incomplete AI response')
    plan = validate_plan(json.loads(raw['response']))
    return plan, raw


def run_steps(plan, send, clock=time.monotonic, sleep=time.sleep):
    """20 Hz open-loop command execution; always attempt a final stop."""
    try:
        for i, step in enumerate(plan['steps'], 1):
            print(f"EXEC {i}: {step['action']} {step['seconds']}s", flush=True)
            end = clock() + step['seconds']
            while clock() < end:
                send(*MOTIONS[step['action']])
                sleep(0.05)
            send(0.0, 0.0)
    finally:
        for _ in range(10):
            send(0.0, 0.0)
            sleep(0.05)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('instruction', nargs='?')
    parser.add_argument('--endpoint', default=os.getenv(
        'OLLAMA_URL', 'http://pai_ai:11434'))
    parser.add_argument('--model', default='qwen2.5:1.5b')
    parser.add_argument('--timeout', type=float, default=180)
    parser.add_argument('--plan-only', action='store_true')
    parser.add_argument('--stop', action='store_true')
    args = parser.parse_args()
    if not args.stop and not args.instruction:
        parser.error('Provide an instruction or --stop')

    # No ROS dependency is imported for --plan-only.
    node = pub = None
    record = None
    log_path = None
    try:
        if not args.plan_only:
            import rclpy
            from rclpy.signals import SignalHandlerOptions
            from geometry_msgs.msg import Twist
            rclpy.init(args=[], signal_handler_options=SignalHandlerOptions.NO)
            node = rclpy.create_node('ai_commander')
            pub = node.create_publisher(Twist, '/cmd_vel', 10)

            def send(v, w):
                msg = Twist()
                msg.linear.x, msg.angular.z = v, w
                pub.publish(msg)

            deadline = time.monotonic() + 8
            while pub.get_subscription_count() == 0:
                if time.monotonic() > deadline:
                    raise RuntimeError('No bridge subscriber on /cmd_vel')
                rclpy.spin_once(node, timeout_sec=0.1)
            for _ in range(10):
                send(0.0, 0.0)
                time.sleep(0.05)
            if args.stop:
                print('STOP sent', flush=True)
                return 0

        print('INPUT:', args.instruction, flush=True)
        print('AI inference running...', flush=True)
        started = time.monotonic()
        plan, raw = infer(args.instruction, args.endpoint, args.model, args.timeout)
        elapsed = round(time.monotonic() - started, 3)
        print('AI PLAN:', json.dumps(plan, ensure_ascii=False), flush=True)
        print(f'Inference: {elapsed}s / model: {args.model}', flush=True)
        logs = Path.home() / 'fortress_ws/demo_logs'
        logs.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
        log_path = logs / (stamp + '.json')
        record = {'instruction': args.instruction, 'model': args.model,
                  'endpoint': args.endpoint, 'inference_seconds': elapsed,
                  'raw_response': raw, 'plan': plan, 'status': 'planned'}
        log_path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
        print('LOG:', log_path.name, flush=True)
        if args.plan_only:
            print('PLAN ONLY: no ROS commands sent', flush=True)
            return 0
        answer = input('Check plan. Press Enter to execute, or q to cancel: ')
        if answer.strip():
            record['status'] = 'cancelled'
            print('CANCELLED', flush=True)
            return 0
        record['status'] = 'executing'
        run_steps(plan, send)
        record['status'] = 'commands_completed'
        print('DONE: commands completed, robot sent STOP', flush=True)
        return 0
    except KeyboardInterrupt:
        if record:
            record['status'] = 'interrupted'
        print('\nINTERRUPTED: sending STOP', flush=True)
        return 130
    except Exception as exc:
        if record:
            record['status'] = 'failed'
            record['error'] = str(exc)
        print('ERROR:', exc, flush=True)
        print('No fixed fallback plan is used.', flush=True)
        return 1
    finally:
        if pub is not None:
            try:
                for _ in range(10):
                    send(0.0, 0.0)
                    time.sleep(0.05)
            finally:
                node.destroy_node()
                rclpy.shutdown()
        if record is not None and log_path:
            log_path.write_text(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    raise SystemExit(main())
