import boto3


NEW_MODEL = "nvidia/nemotron-3.5-embed-1b"


def main() -> None:
    client = boto3.client("lambda", region_name="us-east-2")
    for function_name in ("ActionPlan", "ActionPlanWorker"):
        configuration = client.get_function_configuration(FunctionName=function_name)
        environment = configuration.get("Environment", {}).get("Variables", {})
        environment["EMBEDDING_MODEL"] = NEW_MODEL
        client.update_function_configuration(
            FunctionName=function_name,
            Environment={"Variables": environment},
        )
        print(function_name, "updated")


if __name__ == "__main__":
    main()
