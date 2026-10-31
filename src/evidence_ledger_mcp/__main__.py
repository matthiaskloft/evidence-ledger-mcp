from evidence_ledger_mcp.server import main

if __name__ == "__main__":  # PDF extraction spawns child processes, which import this module
    main()
