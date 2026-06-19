const { Pool } = require('pg');
require('dotenv').config();

// PostgreSQL connection using environment variables
// Make sure you have installed: npm install pg dotenv
const pool = new Pool({
  user: process.env.DB_USER || process.env.POSTGRES_USER || 'postgres',
  host: process.env.DB_HOST || 'localhost',
  database: process.env.DB_NAME || process.env.POSTGRES_DB || 'agile_meeting_db',
  password: process.env.DB_PASSWORD || process.env.POSTGRES_PASSWORD || 'postgres',
  port: parseInt(process.env.DB_PORT || '5432', 10),
});

async function runExample() {
  console.log('Connecting to PostgreSQL database...');
  let client;
  
  try {
    client = await pool.connect();
    console.log('Successfully connected to Agile Meeting DB!\n');

    // Example 1: Fetching meetings
    console.log('--- Fetching Meetings ---');
    const meetingsRes = await client.query('SELECT * FROM meetings ORDER BY created_at DESC LIMIT 5');
    console.table(meetingsRes.rows);

    // Example 2: Fetching User Stories with their associated utterances
    console.log('\n--- Fetching User Stories with Evidence ---');
    const storiesQuery = `
      SELECT 
        us.title AS story_title, 
        us.priority, 
        us.status,
        tu.utterance_text AS evidence
      FROM user_stories us
      LEFT JOIN story_utterance_mapping sum ON us.id = sum.story_id
      LEFT JOIN transcript_utterances tu ON sum.utterance_id = tu.id
    `;
    const storiesRes = await client.query(storiesQuery);
    console.table(storiesRes.rows);

  } catch (err) {
    console.error('Error executing query', err.stack);
  } finally {
    if (client) {
      client.release();
    }
    await pool.end();
  }
}

runExample();
