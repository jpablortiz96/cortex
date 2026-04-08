/**
 * CORTEX — Smart Contract Deployment Script
 * 
 * Deploys:
 * 1. CortexAgentRegistry (agent identities as ERC-721)
 * 2. CortexValidationRegistry (validation artifacts + reputation)
 * 
 * Then registers all 5 trading desk agents on-chain.
 * 
 * Usage:
 *   npx hardhat run scripts/deploy.js --network baseSepolia
 */

const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");

async function main() {
    const [deployer] = await ethers.getSigners();
    
    console.log("");
    console.log("╔══════════════════════════════════════════════╗");
    console.log("║     CORTEX — Deploying ERC-8004 Contracts    ║");
    console.log("╚══════════════════════════════════════════════╝");
    console.log("");
    console.log(`  Deployer: ${deployer.address}`);
    
    const balance = await ethers.provider.getBalance(deployer.address);
    console.log(`  Balance:  ${ethers.formatEther(balance)} ETH`);
    console.log("");

    // ─── Deploy Agent Registry ───
    console.log("1/2 Deploying CortexAgentRegistry...");
    const AgentRegistry = await ethers.getContractFactory("CortexAgentRegistry");
    const agentRegistry = await AgentRegistry.deploy();
    await agentRegistry.waitForDeployment();
    const agentRegistryAddress = await agentRegistry.getAddress();
    console.log(`    ✅ CortexAgentRegistry: ${agentRegistryAddress}`);

    // ─── Deploy Validation Registry ───
    console.log("2/2 Deploying CortexValidationRegistry...");
    const ValidationRegistry = await ethers.getContractFactory("CortexValidationRegistry");
    const validationRegistry = await ValidationRegistry.deploy();
    await validationRegistry.waitForDeployment();
    const validationRegistryAddress = await validationRegistry.getAddress();
    console.log(`    ✅ CortexValidationRegistry: ${validationRegistryAddress}`);

    // ─── Register Agents ───
    console.log("");
    console.log("Registering CORTEX agents on-chain...");

    const agents = [
        {
            role: "strategist",
            name: "CORTEX Strategist",
            metadataURI: "ipfs://cortex/agents/strategist.json",
        },
        {
            role: "risk_officer", 
            name: "CORTEX Risk Officer",
            metadataURI: "ipfs://cortex/agents/risk_officer.json",
        },
        {
            role: "executor",
            name: "CORTEX Executor",
            metadataURI: "ipfs://cortex/agents/executor.json",
        },
        {
            role: "compliance",
            name: "CORTEX Compliance Monitor",
            metadataURI: "ipfs://cortex/agents/compliance.json",
        },
        {
            role: "auditor",
            name: "CORTEX Auditor",
            metadataURI: "ipfs://cortex/agents/auditor.json",
        },
    ];

    const agentTokenIds = {};

    for (const agent of agents) {
        const tx = await agentRegistry.registerAgent(
            agent.role,
            agent.name,
            deployer.address, // All agents share deployer wallet for hackathon
            agent.metadataURI
        );
        const receipt = await tx.wait();
        
        // Get token ID from event
        const event = receipt.logs.find(log => {
            try {
                return agentRegistry.interface.parseLog(log)?.name === "AgentRegistered";
            } catch { return false; }
        });

        let tokenId;
        if (event) {
            const parsed = agentRegistry.interface.parseLog(event);
            tokenId = parsed.args[0].toString();
        } else {
            // Fallback: count from 1
            tokenId = String(Object.keys(agentTokenIds).length + 1);
        }

        agentTokenIds[agent.role] = tokenId;
        console.log(`    ✅ ${agent.name} → Token #${tokenId}`);
    }

    // ─── Save deployment info ───
    const network = await ethers.provider.getNetwork();
    const deployment = {
        network: {
            name: network.name,
            chainId: Number(network.chainId),
        },
        deployer: deployer.address,
        contracts: {
            agentRegistry: agentRegistryAddress,
            validationRegistry: validationRegistryAddress,
        },
        agents: agentTokenIds,
        deployedAt: new Date().toISOString(),
        explorerBaseUrl: network.chainId === 84532n 
            ? "https://sepolia.basescan.org" 
            : "https://etherscan.io",
    };

    // Save to contracts folder
    const deploymentPath = path.join(__dirname, "..", "deployment.json");
    fs.writeFileSync(deploymentPath, JSON.stringify(deployment, null, 2));
    console.log(`\n    📄 Deployment saved to: deployment.json`);

    // Also save to backend for the Python agents to read
    const backendConfigPath = path.join(__dirname, "..", "..", "backend", "deployment.json");
    fs.writeFileSync(backendConfigPath, JSON.stringify(deployment, null, 2));
    console.log(`    📄 Config copied to: backend/deployment.json`);

    // ─── Summary ───
    console.log("");
    console.log("╔══════════════════════════════════════════════╗");
    console.log("║     CORTEX — Deployment Complete! 🎉         ║");
    console.log("╚══════════════════════════════════════════════╝");
    console.log("");
    console.log(`  Agent Registry:      ${agentRegistryAddress}`);
    console.log(`  Validation Registry: ${validationRegistryAddress}`);
    console.log(`  Agents registered:   ${Object.keys(agentTokenIds).length}`);
    console.log("");
    
    if (network.chainId === 84532n) {
        console.log("  🔗 View on BaseScan:");
        console.log(`     ${deployment.explorerBaseUrl}/address/${agentRegistryAddress}`);
        console.log(`     ${deployment.explorerBaseUrl}/address/${validationRegistryAddress}`);
    }
    
    console.log("");
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error("Deployment failed:", error);
        process.exit(1);
    });
