require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config({ path: require("path").join(__dirname, "contracts", ".env") });

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200,
      },
      evmVersion: "cancun",
    },
  },
  defaultNetwork: "sepolia",
  networks: {
    // Ethereum Sepolia Testnet (primary)
    sepolia: {
      url: "https://ethereum-sepolia-rpc.publicnode.com",
      accounts: process.env.DEPLOYER_PRIVATE_KEY
        ? [process.env.DEPLOYER_PRIVATE_KEY]
        : [],
      chainId: 11155111,
    },
    // Base Sepolia Testnet (secondary)
    baseSepolia: {
      url: process.env.BASE_SEPOLIA_RPC || "https://base-sepolia-rpc.publicnode.com",
      accounts: process.env.DEPLOYER_PRIVATE_KEY
        ? [process.env.DEPLOYER_PRIVATE_KEY]
        : [],
      chainId: 84532,
    },
    // Local hardhat for testing
    hardhat: {
      chainId: 31337,
    },
  },
  sourcify: {
    enabled: true,
  },
  etherscan: {
    apiKey: "SZMKB463QFR575NM2178JRAJJ3SK3A6IT3",
    customChains: [
      {
        network: "baseSepolia",
        chainId: 84532,
        urls: {
          apiURL: "https://api-sepolia.basescan.org/api",
          browserURL: "https://sepolia.basescan.org",
        },
      },
    ],
  },
};
