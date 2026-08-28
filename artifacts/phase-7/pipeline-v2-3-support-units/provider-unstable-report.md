# V2.3 paired execution status

The provider preflight and V2.2 baseline completed. The V2.3 support-unit paired run was stopped after bounded provider failures, so no architecture quality decision is valid.

{
  "execution_status": "PROVIDER_UNSTABLE",
  "architecture_decision": "NOT_EVALUATED",
  "required_paired_calls": 55,
  "completed_rows": 32,
  "successful_rows": 30,
  "provider_failures": 2,
  "holdout_rows": 32,
  "acl_rows": 0,
  "quality_comparison_valid": false,
  "reason": "V2.3 support-unit calls timed out/failed before a complete paired holdout was available",
  "failures": [
    {
      "query_id": "multi-01-0",
      "seed": 41,
      "result": "TIMEOUT",
      "error": {
        "message": "Ollama read timeout after 180008.1ms",
        "timeout_type": "READ",
        "type": "OllamaRequestTimeout"
      }
    },
    {
      "query_id": "multi-01-0",
      "seed": 42,
      "result": "TIMEOUT",
      "error": {
        "message": "Ollama read timeout after 180012.0ms",
        "timeout_type": "READ",
        "type": "OllamaRequestTimeout"
      }
    }
  ]
}
