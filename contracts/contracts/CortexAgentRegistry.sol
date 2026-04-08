// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title CortexAgentRegistry
 * @notice ERC-8004 compliant Agent Identity Registry for CORTEX Trading Desk.
 * Each agent in the trading desk gets a unique on-chain identity (ERC-721 NFT).
 * Stores agent metadata: role, capabilities, wallet address, and registration JSON URI.
 */

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract CortexAgentRegistry is ERC721, Ownable {
    
    uint256 private _nextTokenId;

    struct AgentIdentity {
        string role;           // strategist, risk_officer, executor, compliance, auditor
        string name;           // Human-readable name
        address agentWallet;   // Wallet associated with this agent
        string metadataURI;    // URI pointing to Agent Registration JSON
        uint256 registeredAt;  // Block timestamp of registration
        bool active;           // Whether the agent is currently active
    }

    // tokenId => AgentIdentity
    mapping(uint256 => AgentIdentity) public agents;
    
    // role hash => tokenId (for quick lookup by role)
    mapping(bytes32 => uint256) public roleToTokenId;

    // Events
    event AgentRegistered(uint256 indexed tokenId, string role, string name, address agentWallet);
    event AgentDeactivated(uint256 indexed tokenId, string role);
    event AgentMetadataUpdated(uint256 indexed tokenId, string newURI);

    constructor() ERC721("CORTEX Agent Identity", "CORTEX-AGENT") Ownable(msg.sender) {
        _nextTokenId = 1;
    }

    /**
     * @notice Register a new agent identity on-chain.
     * @param role The agent's role in the trading desk
     * @param name Human-readable agent name
     * @param agentWallet The wallet address associated with this agent
     * @param metadataURI URI pointing to the Agent Registration JSON
     */
    function registerAgent(
        string calldata role,
        string calldata name,
        address agentWallet,
        string calldata metadataURI
    ) external onlyOwner returns (uint256) {
        uint256 tokenId = _nextTokenId++;

        _mint(msg.sender, tokenId);

        agents[tokenId] = AgentIdentity({
            role: role,
            name: name,
            agentWallet: agentWallet,
            metadataURI: metadataURI,
            registeredAt: block.timestamp,
            active: true
        });

        roleToTokenId[keccak256(bytes(role))] = tokenId;

        emit AgentRegistered(tokenId, role, name, agentWallet);

        return tokenId;
    }

    /**
     * @notice Get agent identity by token ID.
     */
    function getAgent(uint256 tokenId) external view returns (AgentIdentity memory) {
        require(tokenId > 0 && tokenId < _nextTokenId, "Agent does not exist");
        return agents[tokenId];
    }

    /**
     * @notice Get agent identity by role.
     */
    function getAgentByRole(string calldata role) external view returns (AgentIdentity memory) {
        uint256 tokenId = roleToTokenId[keccak256(bytes(role))];
        require(tokenId > 0, "Role not registered");
        return agents[tokenId];
    }

    /**
     * @notice Deactivate an agent.
     */
    function deactivateAgent(uint256 tokenId) external onlyOwner {
        require(agents[tokenId].active, "Already inactive");
        agents[tokenId].active = false;
        emit AgentDeactivated(tokenId, agents[tokenId].role);
    }

    /**
     * @notice Update agent metadata URI.
     */
    function updateMetadata(uint256 tokenId, string calldata newURI) external onlyOwner {
        require(tokenId > 0 && tokenId < _nextTokenId, "Agent does not exist");
        agents[tokenId].metadataURI = newURI;
        emit AgentMetadataUpdated(tokenId, newURI);
    }

    /**
     * @notice Get total number of registered agents.
     */
    function totalAgents() external view returns (uint256) {
        return _nextTokenId - 1;
    }
}
