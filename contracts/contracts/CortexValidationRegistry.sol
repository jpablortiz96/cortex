// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title CortexValidationRegistry
 * @notice Records validation artifacts for every trading action in the CORTEX desk.
 * Each trade proposal, risk assessment, execution, and compliance check
 * generates an immutable on-chain record — making the trading desk fully auditable.
 * 
 * This is the core of "trustless" — anyone can verify that agents followed their rules.
 */

import "@openzeppelin/contracts/access/Ownable.sol";

contract CortexValidationRegistry is Ownable {

    enum ValidationType {
        TRADE_PROPOSAL,      // 0 - Strategist proposed a trade
        RISK_APPROVED,       // 1 - Risk Officer approved
        RISK_VETOED,         // 2 - Risk Officer vetoed
        TRADE_EXECUTED,      // 3 - Executor executed the trade
        COMPLIANCE_CLEAR,    // 4 - Compliance check passed
        COMPLIANCE_ALERT,    // 5 - Compliance raised an alert
        CIRCUIT_BREAKER      // 6 - Circuit breaker triggered
    }

    struct ValidationArtifact {
        uint256 id;
        uint256 agentTokenId;    // Reference to CortexAgentRegistry
        ValidationType vType;
        string tradeId;          // Internal trade proposal ID
        string dataHash;         // Hash of the full decision data (for verification)
        string summary;          // Human-readable summary of the action
        uint256 timestamp;
        uint256 cycleNumber;     // Trading cycle number
    }

    uint256 private _nextId;
    
    // All validation artifacts
    mapping(uint256 => ValidationArtifact) public artifacts;
    
    // tradeId => list of artifact IDs (to see full lifecycle of a trade)
    mapping(string => uint256[]) public tradeArtifacts;
    
    // Agent reputation scores
    mapping(uint256 => AgentReputation) public reputation;

    struct AgentReputation {
        uint256 totalActions;
        uint256 approvals;
        uint256 vetoes;
        uint256 successfulTrades;
        uint256 compliancePasses;
        uint256 complianceAlerts;
        int256 reputationScore;    // Can go negative
    }

    // Events — these are what indexers and dashboards can listen to
    event ValidationRecorded(
        uint256 indexed id,
        uint256 indexed agentTokenId,
        ValidationType vType,
        string tradeId,
        string summary
    );

    event ReputationUpdated(
        uint256 indexed agentTokenId,
        int256 newScore,
        uint256 totalActions
    );

    event CircuitBreakerTriggered(
        string tradeId,
        uint256 cycleNumber,
        string reason
    );

    constructor() Ownable(msg.sender) {
        _nextId = 1;
    }

    /**
     * @notice Record a validation artifact on-chain.
     * @param agentTokenId The agent's token ID from CortexAgentRegistry
     * @param vType The type of validation being recorded
     * @param tradeId The internal trade proposal ID
     * @param dataHash Hash of the complete decision data
     * @param summary Human-readable summary
     * @param cycleNumber The trading cycle this belongs to
     */
    function recordValidation(
        uint256 agentTokenId,
        ValidationType vType,
        string calldata tradeId,
        string calldata dataHash,
        string calldata summary,
        uint256 cycleNumber
    ) external onlyOwner returns (uint256) {
        uint256 artifactId = _nextId++;

        artifacts[artifactId] = ValidationArtifact({
            id: artifactId,
            agentTokenId: agentTokenId,
            vType: vType,
            tradeId: tradeId,
            dataHash: dataHash,
            summary: summary,
            timestamp: block.timestamp,
            cycleNumber: cycleNumber
        });

        tradeArtifacts[tradeId].push(artifactId);

        // Update reputation
        _updateReputation(agentTokenId, vType);

        emit ValidationRecorded(artifactId, agentTokenId, vType, tradeId, summary);

        if (vType == ValidationType.CIRCUIT_BREAKER) {
            emit CircuitBreakerTriggered(tradeId, cycleNumber, summary);
        }

        return artifactId;
    }

    /**
     * @notice Get all validation artifacts for a specific trade.
     */
    function getTradeValidations(string calldata tradeId) 
        external view returns (uint256[] memory) 
    {
        return tradeArtifacts[tradeId];
    }

    /**
     * @notice Get a specific validation artifact.
     */
    function getArtifact(uint256 artifactId) 
        external view returns (ValidationArtifact memory) 
    {
        require(artifactId > 0 && artifactId < _nextId, "Artifact does not exist");
        return artifacts[artifactId];
    }

    /**
     * @notice Get agent reputation.
     */
    function getReputation(uint256 agentTokenId) 
        external view returns (AgentReputation memory) 
    {
        return reputation[agentTokenId];
    }

    /**
     * @notice Get total number of validation artifacts.
     */
    function totalArtifacts() external view returns (uint256) {
        return _nextId - 1;
    }

    // ─── Internal ───

    function _updateReputation(uint256 agentTokenId, ValidationType vType) internal {
        AgentReputation storage rep = reputation[agentTokenId];
        rep.totalActions++;

        if (vType == ValidationType.RISK_APPROVED) {
            rep.approvals++;
            rep.reputationScore += 1;
        } else if (vType == ValidationType.RISK_VETOED) {
            rep.vetoes++;
            rep.reputationScore += 2; // Vetoing is good risk management
        } else if (vType == ValidationType.TRADE_EXECUTED) {
            rep.successfulTrades++;
            rep.reputationScore += 1;
        } else if (vType == ValidationType.COMPLIANCE_CLEAR) {
            rep.compliancePasses++;
            rep.reputationScore += 1;
        } else if (vType == ValidationType.COMPLIANCE_ALERT) {
            rep.complianceAlerts++;
            rep.reputationScore -= 2;
        } else if (vType == ValidationType.CIRCUIT_BREAKER) {
            rep.reputationScore -= 5;
        }

        emit ReputationUpdated(agentTokenId, rep.reputationScore, rep.totalActions);
    }
}
