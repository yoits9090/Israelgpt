require('dotenv').config();
const { Client } = require('discord.js-selfbot-v13');
const config = require('./config.json');

const TOKEN = process.env.token;
if (!TOKEN) {
  console.error('Missing token in .env (expected variable "token")');
  process.exit(1);
}

async function bumpWithChannel(channelId) {
  const client = new Client();

  return new Promise((resolve) => {
    client.on('ready', async () => {
      console.log(`Logged in as ${client.user.tag} for channel ${channelId}`);

      try {
        const channel = await client.channels.fetch(channelId);
        await channel.sendSlash('302050872383242240', 'bump');
        console.log(`Bump command sent successfully by ${client.user.tag}`);
      } catch (error) {
        console.error(`Failed to send bump command for channel ${channelId}:`, error.message);
      } finally {
        client.destroy(); 
        resolve();
      }
    });

    client.login(TOKEN).catch((err) => {
      console.error('Failed to login with bump token:', err.message);
      resolve();
    });
  });
}

async function startBumpLoop() {
  while (true) {
    for (const account of config.accounts) {
      console.log(`Processing bump for channel: ${account.channelId}...`);
      await bumpWithChannel(account.channelId); 

      console.log(`Waiting 5 seconds before the next bump...`);
      await new Promise((resolve) => setTimeout(resolve, 5000)); // Wait 5 seconds
    }

    // After all tokens have sent the bump command, wait 2 hours and 15 minutes (8100000ms)
    console.log(`All accounts have sent the bump. Waiting 2 hours and 15 minutes before restarting...`);
    await new Promise((resolve) => setTimeout(resolve, 8100000));
  }
}

startBumpLoop();