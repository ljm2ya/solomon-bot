#!/usr/bin/env node

const { NotionAPI } = require('notion-client');

async function fetchNotionPage(pageId) {
    try {
        const notion = new NotionAPI();

        // Extract page ID from URL if needed
        let cleanPageId = pageId;
        if (pageId.includes('notion.so')) {
            const match = pageId.match(/([a-f0-9]{32}|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/i);
            if (match) {
                cleanPageId = match[1].replace(/-/g, '');
            }
        }

        // Debug output to stderr to not interfere with JSON output
        console.error(`Fetching Notion page: ${cleanPageId}`);

        // Get page content
        const recordMap = await notion.getPage(cleanPageId);

        if (!recordMap || !recordMap.block) {
            throw new Error('Failed to fetch page content');
        }

        // Extract text content from blocks
        const blocks = Object.values(recordMap.block);
        let textContent = [];

        for (const block of blocks) {
            const blockData = block.value;
            if (blockData && blockData.properties && blockData.properties.title) {
                const title = blockData.properties.title[0];
                if (Array.isArray(title)) {
                    textContent.push(title[0]);
                } else if (typeof title === 'string') {
                    textContent.push(title);
                }
            }
        }

        const content = textContent.join(' ').trim();

        if (content.length === 0) {
            throw new Error('No readable content found in page');
        }

        return {
            success: true,
            content: content,
            length: content.length
        };

    } catch (error) {
        return {
            success: false,
            error: error.message,
            content: null
        };
    }
}

// Handle command line arguments
if (require.main === module) {
    const pageId = process.argv[2];
    if (!pageId) {
        console.error('Usage: node notion_fetcher.js <page-id-or-url>');
        process.exit(1);
    }

    fetchNotionPage(pageId)
        .then(result => {
            console.log(JSON.stringify(result, null, 2));
        })
        .catch(error => {
            console.error(JSON.stringify({
                success: false,
                error: error.message,
                content: null
            }));
        });
}

module.exports = { fetchNotionPage };