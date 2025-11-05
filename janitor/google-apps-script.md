
# Google Apps Script for Slack Janitor Duty Notifications

This document contains the complete Google Apps Script and setup instructions for automatically sending janitor duty notifications to Slack every Monday.

## Overview

The script reads janitor duty assignments from a Google Sheet and sends formatted notifications to a Slack channel every Monday morning. It shows both the current week's duty person and next week's assignment.

## Google Apps Script Code

```javascript
/**
 * Google Apps Script for Janitor Duty Slack Notifications
 * 
 * Setup Instructions:
 * 1. Create a Google Sheet with your janitor rota data
 * 2. Set up a Slack webhook URL
 * 3. Configure the script with your sheet ID and webhook URL
 * 4. Set up a time-driven trigger for Monday mornings
 */

// Configuration - Update these values
const CONFIG = {
  // Your Google Sheet ID (from the URL)
  SHEET_ID: 'YOUR_GOOGLE_SHEET_ID_HERE',
  
  // Slack webhook URL for your channel (optional - can use bot token instead)
  SLACK_WEBHOOK_URL: 'YOUR_SLACK_WEBHOOK_URL_HERE',
  
  // Slack Bot Token for posting messages and pinning (required for pinning)
  // Get this from OAuth & Permissions in your Slack app settings
  SLACK_BOT_TOKEN: 'YOUR_SLACK_BOT_TOKEN_HERE',
  
  // Slack Channel ID (required for pinning)
  // Right-click on channel → View channel details → Copy Channel ID
  SLACK_CHANNEL_ID: 'YOUR_SLACK_CHANNEL_ID_HERE',
  
  // Whether to pin the message automatically (requires bot token and channel ID)
  PIN_MESSAGE: true,
  
  // Sheet name containing the rota data
  SHEET_NAME: 'Janitor Rota',
  
  // Column names in your sheet
  START_DATE_COLUMN: 'Start date',
  PERSON_COLUMN: 'Person'
};

/**
 * Main function to send janitor duty notification
 * This function will be called by the time-driven trigger
 */
function sendJanitorDutyNotification() {
  try {
    const dutyInfo = getCurrentWeekDuty();
    
    if (dutyInfo.currentPerson) {
      const message = formatSlackMessage(dutyInfo);
      
      // Use bot token if available (for pinning support), otherwise fall back to webhook
      let messageTimestamp = null;
      if (CONFIG.SLACK_BOT_TOKEN && CONFIG.SLACK_CHANNEL_ID) {
        messageTimestamp = sendToSlackWithAPI(message);
      } else {
        sendToSlack(message);
      }
      
      // Pin the message if enabled and we have the timestamp
      if (CONFIG.PIN_MESSAGE && messageTimestamp && CONFIG.SLACK_BOT_TOKEN && CONFIG.SLACK_CHANNEL_ID) {
        pinMessage(messageTimestamp);
      }
      
      // Log the notification
      console.log(`Notification sent: ${dutyInfo.currentPerson} is on duty this week`);
      if (messageTimestamp && CONFIG.PIN_MESSAGE) {
        console.log('Message pinned successfully');
      }
    } else {
      console.log('No duty assignment found for this week');
    }
  } catch (error) {
    console.error('Error sending janitor duty notification:', error);
    
    // Send error notification to Slack
    const errorMessage = {
      text: `⚠️ Error sending janitor duty notification: ${error.message}`,
      username: 'Janitor Bot',
      icon_emoji: ':warning:'
    };
    if (CONFIG.SLACK_BOT_TOKEN && CONFIG.SLACK_CHANNEL_ID) {
      sendToSlackWithAPI(errorMessage);
    } else {
      sendToSlack(errorMessage);
    }
  }
}

/**
 * Get current week's duty information from the Google Sheet
 */
function getCurrentWeekDuty() {
  const sheet = SpreadsheetApp.openById(CONFIG.SHEET_ID).getSheetByName(CONFIG.SHEET_NAME);
  const data = sheet.getDataRange().getValues();
  
  // Skip header row
  const rows = data.slice(1);
  
  const today = new Date();
  const currentWeekStart = getMondayOfWeek(today);
  
  let currentPerson = null;
  let currentStartDate = null;
  let currentEndDate = null;
  let nextPerson = null;
  let nextStartDate = null;
  let nextEndDate = null;
  
  // Find current week's assignment
  for (let i = 0; i < rows.length; i++) {
    const row = rows[i];
    const startDate = new Date(row[0]); // Assuming date is in first column
    const person = row[1]; // Assuming person is in second column
    
    // Calculate end date (Monday to Friday)
    const endDate = new Date(startDate);
    endDate.setDate(endDate.getDate() + 4);
    
    // Check if current week falls within this duty period
    if (startDate <= currentWeekStart && currentWeekStart <= endDate) {
      currentPerson = person;
      currentStartDate = startDate;
      currentEndDate = endDate;
      
      // Get next week's person
      if (i + 1 < rows.length) {
        const nextRow = rows[i + 1];
        nextPerson = nextRow[1];
        nextStartDate = new Date(nextRow[0]);
        nextEndDate = new Date(nextStartDate);
        nextEndDate.setDate(nextEndDate.getDate() + 4);
      }
      break;
    }
  }
  
  return {
    currentPerson,
    currentStartDate,
    currentEndDate,
    nextPerson,
    nextStartDate,
    nextEndDate
  };
}

/**
 * Get the Monday of the current week
 */
function getMondayOfWeek(date) {
  const day = date.getDay();
  const diff = date.getDate() - day + (day === 0 ? -6 : 1); // Adjust when day is Sunday
  const monday = new Date(date.setDate(diff));
  monday.setHours(0, 0, 0, 0);
  return monday;
}

/**
 * Format the duty information into a Slack message
 */
function formatSlackMessage(dutyInfo) {
  const currentWeek = formatDateRange(dutyInfo.currentStartDate, dutyInfo.currentEndDate);
  const nextWeek = dutyInfo.nextPerson ? formatDateRange(dutyInfo.nextStartDate, dutyInfo.nextEndDate) : 'TBD';
  
  const message = {
    text: `🗓️ *Janitor Duty This Week*`,
    username: 'Janitor Bot',
    icon_emoji: ':broom:',
    attachments: [
      {
        color: '#36a64f',
        fields: [
          {
            title: 'This Week',
            value: `*${dutyInfo.currentPerson}* (${currentWeek})`,
            short: true
          },
          {
            title: 'Next Week',
            value: `*${dutyInfo.nextPerson || 'TBD'}* (${nextWeek})`,
            short: true
          }
        ],
        footer: 'Janitor Duty Rota',
        ts: Math.floor(Date.now() / 1000)
      }
    ]
  };
  
  return message;
}

/**
 * Send message to Slack via webhook (fallback method)
 */
function sendToSlack(message) {
  const payload = JSON.stringify(message);
  
  const options = {
    method: 'POST',
    contentType: 'application/json',
    payload: payload
  };
  
  const response = UrlFetchApp.fetch(CONFIG.SLACK_WEBHOOK_URL, options);
  
  if (response.getResponseCode() !== 200) {
    throw new Error(`Slack API error: ${response.getResponseCode()} - ${response.getContentText()}`);
  }
  
  return response;
}

/**
 * Send message to Slack via Web API (chat.postMessage)
 * This method returns the message timestamp needed for pinning
 */
function sendToSlackWithAPI(message) {
  const url = 'https://slack.com/api/chat.postMessage';
  
  // Convert webhook format to API format
  const apiPayload = {
    channel: CONFIG.SLACK_CHANNEL_ID,
    text: message.text,
    username: message.username,
    icon_emoji: message.icon_emoji,
    attachments: message.attachments
  };
  
  const options = {
    method: 'POST',
    contentType: 'application/json',
    headers: {
      'Authorization': `Bearer ${CONFIG.SLACK_BOT_TOKEN}`
    },
    payload: JSON.stringify(apiPayload)
  };
  
  const response = UrlFetchApp.fetch(url, options);
  const responseCode = response.getResponseCode();
  const responseText = response.getContentText();
  const responseData = JSON.parse(responseText);
  
  if (responseCode !== 200 || !responseData.ok) {
    throw new Error(`Slack API error: ${responseCode} - ${responseData.error || responseText}`);
  }
  
  // Return the message timestamp for pinning
  return responseData.ts;
}

/**
 * Pin a message in Slack using the pins.add API
 */
function pinMessage(messageTimestamp) {
  try {
    const url = 'https://slack.com/api/pins.add';
    const payload = {
      channel: CONFIG.SLACK_CHANNEL_ID,
      timestamp: messageTimestamp
    };
    
    const options = {
      method: 'POST',
      contentType: 'application/x-www-form-urlencoded',
      headers: {
        'Authorization': `Bearer ${CONFIG.SLACK_BOT_TOKEN}`
      },
      payload: Object.keys(payload).map(key => `${encodeURIComponent(key)}=${encodeURIComponent(payload[key])}`).join('&')
    };
    
    const response = UrlFetchApp.fetch(url, options);
    const responseCode = response.getResponseCode();
    const responseText = response.getContentText();
    const responseData = JSON.parse(responseText);
    
    if (responseCode !== 200 || !responseData.ok) {
      console.warn(`Failed to pin message: ${responseData.error || responseText}`);
      // Don't throw - pinning is optional, don't fail the whole notification
      return false;
    }
    
    console.log('Message pinned successfully');
    return true;
  } catch (error) {
    console.warn('Error pinning message:', error);
    // Don't throw - pinning is optional
    return false;
  }
}

/**
 * Format date range for display
 */
function formatDateRange(startDate, endDate) {
  const start = new Date(startDate);
  const end = new Date(endDate);
  
  if (start.getMonth() === end.getMonth()) {
    return `${start.getDate()}-${end.getDate()}.${(start.getMonth() + 1).toString().padStart(2, '0')}`;
  } else {
    return `${start.getDate()}.${(start.getMonth() + 1).toString().padStart(2, '0')}-${end.getDate()}.${(end.getMonth() + 1).toString().padStart(2, '0')}`;
  }
}

/**
 * Test function to manually trigger the notification
 * Use this to test your setup before setting up the automatic trigger
 */
function testNotification() {
  sendJanitorDutyNotification();
}

/**
 * Setup function to create the time-driven trigger
 * Run this once to set up automatic Monday morning notifications
 */
function setupTrigger() {
  // Delete existing triggers for this function
  const triggers = ScriptApp.getProjectTriggers();
  triggers.forEach(trigger => {
    if (trigger.getHandlerFunction() === 'sendJanitorDutyNotification') {
      ScriptApp.deleteTrigger(trigger);
    }
  });
  
  // Create new trigger for every Monday at 9:00 AM
  ScriptApp.newTrigger('sendJanitorDutyNotification')
    .timeBased()
    .everyWeeks(1)
    .onWeekDay(ScriptApp.WeekDay.MONDAY)
    .atHour(9)
    .create();
    
  console.log('Trigger created: Janitor duty notifications will be sent every Monday at 9:00 AM');
}
```

## Setup Instructions

### Step 1: Create Google Sheet

1. **Create a new Google Sheet**
   - Go to [sheets.google.com](https://sheets.google.com)
   - Click "Blank" to create a new sheet

2. **Add your janitor rota data**
   - Copy the data from your `janitor-rota.txt` file
   - Paste it into the sheet starting from cell A1
   - Ensure the first row contains headers: "Start date" and "Person"
   - Make sure dates are in MM/DD/YYYY format

3. **Get the Sheet ID**
   - Look at the URL of your sheet
   - Copy the long string between `/d/` and `/edit`
   - Example: `https://docs.google.com/spreadsheets/d/1ABC123DEF456GHI789JKL/edit`
   - Sheet ID would be: `1ABC123DEF456GHI789JKL`

### Step 2: Set up Slack App and Bot Token

**Important:** To enable automatic message pinning, you need to use a Slack Bot Token instead of (or in addition to) a webhook. The bot token method also allows pinning messages automatically.

1. **Go to your Slack workspace**
   - Navigate to [api.slack.com](https://api.slack.com)

2. **Create a new app**
   - Click "Create New App"
   - Choose "From scratch"
   - Give it a name like "Janitor Bot"
   - Select your workspace

3. **Enable OAuth Scopes (Required for pinning)**
   - In your app settings, go to "OAuth & Permissions"
   - Scroll down to "Scopes" → "Bot Token Scopes"
   - Add the following scopes:
     - `chat:write` (to post messages)
     - `pins:write` (to pin messages)
     - `channels:read` (to read channel information)
   
4. **Install the app to your workspace**
   - Scroll up to "OAuth Tokens for Your Workspace"
   - Click "Install to Workspace"
   - Review and authorize the permissions
   - Copy the "Bot User OAuth Token" (starts with `xoxb-...`)
   - This is your `SLACK_BOT_TOKEN`

5. **Get your Channel ID**
   - In Slack, open your channel
   - Right-click on the channel name in the sidebar
   - Select "View channel details" or "Open channel details"
   - Scroll down to find the Channel ID (or copy it from the channel URL)
   - Channel ID format: `C1234567890` or `G1234567890` for private channels
   - Alternatively, you can get it from the channel URL: `https://yourworkspace.slack.com/archives/C1234567890`

**Optional: Set up Webhook (Fallback)**
   - If you want to keep webhook as a fallback, go to "Incoming Webhooks"
   - Toggle "Activate Incoming Webhooks" to On
   - Click "Add New Webhook to Workspace"
   - Choose the channel where you want notifications
   - Click "Allow"
   - Copy the webhook URL (starts with `https://hooks.slack.com/services/...`)
   - Note: Webhooks cannot pin messages, so bot token is required for pinning

### Step 3: Configure the Google Apps Script

1. **Open Apps Script**
   - In your Google Sheet, go to Extensions → Apps Script
   - This opens the Google Apps Script editor

2. **Replace the default code**
   - Delete the default `myFunction()` code
   - Paste the entire script from above

3. **Update the configuration**
   - Find the `CONFIG` object at the top of the script
   - Replace `YOUR_GOOGLE_SHEET_ID_HERE` with your actual Sheet ID
   - Replace `YOUR_SLACK_BOT_TOKEN_HERE` with your Bot User OAuth Token (required for pinning)
   - Replace `YOUR_SLACK_CHANNEL_ID_HERE` with your channel ID (required for pinning)
   - (Optional) Replace `YOUR_SLACK_WEBHOOK_URL_HERE` with your Slack webhook URL (only needed as fallback)
   - Set `PIN_MESSAGE: true` to enable automatic pinning (default is enabled)
   - Update `SHEET_NAME` if your sheet tab has a different name
   
   **Note:** If you provide the bot token and channel ID, the script will use the Web API to post messages (which enables pinning). If you don't provide them, it will fall back to webhooks (but pinning won't work).

4. **Save the script**
   - Click the save icon or press Ctrl+S
   - Give your project a name like "Janitor Duty Notifications"

### Step 4: Test the Setup

1. **Run the test function**
   - In the Apps Script editor, select `testNotification` from the function dropdown
   - Click the "Run" button (▶️)
   - Grant permissions when prompted
   - Check your Slack channel for the test notification

2. **Verify the data**
   - Make sure the notification shows the correct person and dates
   - Check that the formatting looks good

### Step 5: Set up Automatic Notifications

1. **Create the trigger**
   - In the Apps Script editor, select `setupTrigger` from the function dropdown
   - Click the "Run" button
   - This creates a trigger that runs every Monday at 9:00 AM

2. **Verify the trigger**
   - Go to Triggers in the left sidebar (clock icon)
   - You should see a trigger for `sendJanitorDutyNotification`
   - It should be set to run "Every week on Monday at 9:00 AM"

## Troubleshooting

### Common Issues

1. **"Script function not found" error**
   - Make sure you've saved the script
   - Check that the function name is spelled correctly

2. **"Permission denied" error**
   - Grant all requested permissions
   - You may need to authorize the script multiple times

3. **"Sheet not found" error**
   - Verify your Sheet ID is correct
   - Make sure the sheet name matches exactly (case-sensitive)

4. **Slack webhook not working**
   - Verify the webhook URL is correct
   - Make sure the webhook is active in your Slack app settings
   - Note: If using bot token, webhook is optional and only used as fallback

5. **Message not pinning**
   - Verify your Bot Token is correct and starts with `xoxb-`
   - Check that you've installed the app to your workspace after adding OAuth scopes
   - Verify the Channel ID is correct (should start with `C` for public channels or `G` for private channels)
   - Make sure you've added the required OAuth scopes: `chat:write` and `pins:write`
   - Check that `PIN_MESSAGE` is set to `true` in the CONFIG
   - Check the Apps Script execution log for specific error messages
   - Note: Pinning failures won't prevent the message from being posted

6. **No notification sent**
   - Check the Apps Script execution log
   - Look for error messages in the console
   - Verify your sheet data format matches expectations
   - If using bot token, verify you have `chat:write` scope enabled

### Testing Commands

- **Test notification**: Run `testNotification()` function
- **Check current duty**: Run `getCurrentWeekDuty()` function
- **View logs**: Go to Executions in the Apps Script editor

## Message Pinning

The script can automatically pin the duty notification message to the channel so it's always visible at the top. This is especially useful for important announcements like janitor duty rota.

### How Pinning Works

- **Automatic Pinning**: When `PIN_MESSAGE: true` is set in the CONFIG, the script will automatically pin each duty notification message after posting it.
- **Visibility**: Pinned messages appear when users click the pin icon at the top of the channel, making them easily accessible.
- **Requirements**: To enable pinning, you must provide:
  - `SLACK_BOT_TOKEN`: Your bot's OAuth token
  - `SLACK_CHANNEL_ID`: The channel where messages are posted
  - OAuth scopes: `chat:write` and `pins:write`

### Disabling Pinning

If you don't want messages to be pinned automatically, set `PIN_MESSAGE: false` in the CONFIG object.

### Pinning Limits

- Each Slack channel can have up to 100 pinned items
- The script will pin each new notification, so old pins may accumulate
- Consider manually unpinning old duty notifications periodically

## Customization Options

### Change Notification Time
```javascript
// In setupTrigger() function, change the hour:
.atHour(8)  // 8:00 AM instead of 9:00 AM
```

### Change Message Format
Modify the `formatSlackMessage()` function to customize:
- Message text
- Colors
- Emojis
- Field names

### Add More Information
You can extend the script to include:
- Duty responsibilities
- Contact information
- Reminder messages
- Historical data

## Security Notes

- Keep your webhook URL private
- Don't share the Apps Script with sensitive data
- Regularly review and update permissions
- Consider using service accounts for production use

## Support

If you encounter issues:
1. Check the Apps Script execution logs
2. Verify all configuration values are correct
3. Test individual functions to isolate problems
4. Check Slack webhook status in your app settings
