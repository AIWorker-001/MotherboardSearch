from pathlib import Path
import json,subprocess,sys

def test_socket_benchmark_evaluator(tmp_path:Path):
 results=tmp_path/'results.json';benchmark=tmp_path/'benchmark.json';output=tmp_path/'out.json'
 results.write_text(json.dumps([{'item_id':'1','cpu_state':'empty_socket_likely','socket_localized_images':1}]))
 benchmark.write_text(json.dumps({'items':[{'item_id':'1','expected_cpu_state':'empty_socket_likely'}]}))
 subprocess.run([sys.executable,'src/evaluate_socket_first.py','--results',str(results),'--benchmark',str(benchmark),'--output',str(output)],check=True,capture_output=True)
 assert json.loads(output.read_text())['accuracy']==1.0
