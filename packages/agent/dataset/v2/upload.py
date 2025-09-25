from huggingface_hub import HfApi, upload_folder

# ===== CONFIG (edit) ===========================
REPO_ID = "keonoh00/static-software-analysis-dataset"  # e.g., "ksign-lab/cwe-ast-v1"
PRIVATE = True  # True or False
FOLDER = "../../data/v2"  # must contain README.md and data/
# ==============================================


def main():
    api = HfApi()
    api.create_repo(
        repo_id=REPO_ID, repo_type="dataset", private=PRIVATE, exist_ok=True
    )
    upload_folder(repo_id=REPO_ID, repo_type="dataset", folder_path=FOLDER)
    print(f"Uploaded {FOLDER} → {REPO_ID}")


if __name__ == "__main__":
    main()
