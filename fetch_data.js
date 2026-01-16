#!/usr/bin/env node
/**
 * Fetch data from USRIOT dashboard using Node.js + jsdom
 * This renders JavaScript and extracts the data
 */

const https = require('https');
const url = process.argv[2] || 'https://mp.usriot.com/draw/show.html?lang=en&lightbox=1&highlight=0000ff&layers=1&nav=1&title=FIT100%20Main%20Inflow%20Lismore%20STP&id=97811&link=Lpu7Q2CM3osZ&model=1&cusdeviceNo=0000088831000010&share=48731ec89bf8108b2a451fbffa590da4f0cf419a5623beb7d48c1060e3f0dbe177e28054c26be49bbabca1da5b977e7c16a47891d94f70a08a876d24c55416854700de7cc51a06f8e102798d6ecc39478ef1394a246efa109e6c6358e30a259010a5c403c71756173c90cf1e10ced6fdf54d90881c05559f2c8c5717ee8109210672fa3574a9c04a465bc0df8b9c354da487a7bcb6679a7ec32276ba3610301be80d8c7588ef1797ca01fb6b87e74a8b6e5cd0ac668918d02ae99a7966f57ecf603b63a12d4b0a160d3ac0920254d6836f1e26d244412f82859f7f7b0df7b8406e95ef97a7cb2302a07826d3b8cba81721c5bce1d7e9bf0b01f32d1d0330a44301a1ab0f';

console.log('Fetching data from:', url.substring(0, 100) + '...');

https.get(url, (res) => {
  let data = '';
  
  res.on('data', (chunk) => {
    data += chunk;
  });
  
  res.on('end', () => {
    // Extract text content and look for patterns
    const textContent = data
      .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '') // Remove scripts
      .replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, '') // Remove styles
      .replace(/<[^>]+>/g, ' ') // Remove HTML tags
      .replace(/\s+/g, ' '); // Collapse whitespace
    
    console.log('\n📄 Page text (first 1000 chars):');
    console.log(textContent.substring(0, 1000));
    
    // Look for specific patterns
    const depthMatch = textContent.match(/depth[:\s]+(\d+\.?\d*)/i);
    const velocityMatch = textContent.match(/velocity[:\s]+(\d+\.?\d*)/i);
    const flowMatch = textContent.match(/flow[:\s]+(\d+\.?\d*)/i);
    
    console.log('\n📊 Extracted patterns:');
    console.log('Depth:', depthMatch ? depthMatch[1] : 'NOT FOUND');
    console.log('Velocity:', velocityMatch ? velocityMatch[1] : 'NOT FOUND');
    console.log('Flow:', flowMatch ? flowMatch[1] : 'NOT FOUND');
    
    // Check if the page has actual content
    if (textContent.toLowerCase().includes('depth') || 
        textContent.toLowerCase().includes('velocity') ||
        textContent.toLowerCase().includes('flow')) {
      console.log('\n✅ Found sensor keywords in page');
    } else {
      console.log('\n⚠️  No sensor keywords found - page may require JavaScript');
    }
  });
}).on('error', (e) => {
  console.error('Error:', e.message);
});
