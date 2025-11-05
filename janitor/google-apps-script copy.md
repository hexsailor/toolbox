
# Google Apps Script for Slack Janitor Duty Notifications

This document contains the complete Google Apps Script and setup instructions for automatically sending janitor duty notifications to Slack every Monday.

## Overview

The script reads janitor duty assignments from a Google Sheet and sends formatted notifications to a Slack channel every Monday morning. It shows both the current week's duty person and next week's assignment.

**Bonus Feature:** The script can also automatically update the Slack channel's overview/description (the "About" section) with the current duty information, so team members can see who is on duty at a glance without scrolling through messages.

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
  
  // Slack webhook URL for your channel
  SLACK_WEBHOOK_URL: 'YOUR_SLACK_WEBHOOK_URL_HERE',
  
  // Slack Bot Token for updating channel overview (optional - only needed if updating channel description)
  // Get this from OAuth & Permissions in your Slack app settings
  SLACK_BOT_TOKEN: 'YOUR_SLACK_BOT_TOKEN_HERE',
  
  // Slack Channel ID (optional - only needed if updating channel description)
  // Right-click on channel → View channel details → Copy Channel ID
  SLACK_CHANNEL_ID: 'YOUR_SLACK_CHANNEL_ID_HERE',
  
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
      sendToSlack(message);
      
      // Update channel overview with the same information
      if (CONFIG.SLACK_BOT_TOKEN && CONFIG.SLACK_CHANNEL_ID) {
        updateSlackChannelOverview(dutyInfo);
      }
      
      // Log the notification
      console.log(`Notification sent: ${dutyInfo.currentPerson} is on duty this week`);
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
    sendToSlack(errorMessage);
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
 * Send message to Slack via webhook
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
 * Update Slack channel overview (description/purpose) with duty information
 * This uses the Slack Web API conversations.setPurpose method
 * It preserves existing content and updates only the duty section
 */
function updateSlackChannelOverview(dutyInfo) {
  try {
    // First, get the current channel purpose to preserve existing content
    const currentPurpose = getCurrentChannelPurpose();
    
    const currentWeek = formatDateRange(dutyInfo.currentStartDate, dutyInfo.currentEndDate);
    const nextWeek = dutyInfo.nextPerson ? formatDateRange(dutyInfo.nextStartDate, dutyInfo.nextEndDate) : 'TBD';
    
    // Format the duty information
    const dutyText = formatChannelOverviewText(dutyInfo, currentWeek, nextWeek);
    
    // Merge with existing content, removing old duty info if present
    const updatedPurpose = mergeChannelOverview(currentPurpose, dutyText);
    
    // Update the channel purpose
    const url = 'https://slack.com/api/conversations.setPurpose';
    const payload = {
      channel: CONFIG.SLACK_CHANNEL_ID,
      purpose: updatedPurpose
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
      throw new Error(`Slack API error: ${responseCode} - ${responseData.error || responseText}`);
    }
    
    console.log('Channel overview updated successfully');
    return responseData;
  } catch (error) {
    console.error('Error updating channel overview:', error);
    // Don't throw - we don't want to fail the whole notification if overview update fails
    return null;
  }
}

/**
 * Get the current channel purpose/description
 */
function getCurrentChannelPurpose() {
  try {
    const url = 'https://slack.com/api/conversations.info';
    const params = `channel=${encodeURIComponent(CONFIG.SLACK_CHANNEL_ID)}`;
    
    const options = {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${CONFIG.SLACK_BOT_TOKEN}`
      }
    };
    
    const response = UrlFetchApp.fetch(`${url}?${params}`, options);
    const responseCode = response.getResponseCode();
    const responseText = response.getContentText();
    const responseData = JSON.parse(responseText);
    
    if (responseCode !== 200 || !responseData.ok) {
      console.warn(`Could not retrieve current channel purpose: ${responseData.error || responseText}`);
      return '';
    }
    
    return responseData.channel.purpose?.value || '';
  } catch (error) {
    console.warn('Error getting current channel purpose:', error);
    return '';
  }
}

/**
 * Merge existing channel overview with new duty information
 * Removes old duty info if present and adds/updates the new duty section
 */
function mergeChannelOverview(currentPurpose, dutyText) {
  if (!currentPurpose || currentPurpose.trim() === '') {
    // No existing content, just return the duty text
    return dutyText;
  }
  
  // Remove old duty information if it exists
  // Look for patterns like "🗓️ Janitor Duty Rota" or "Janitor Duty" sections
  const dutyPatterns = [
    /🗓️\s*Janitor\s*Duty\s*Rota[\s\S]*?(?=\n\n|\n[A-Z]|$)/i,
    /Janitor\s*Duty\s*Rota[\s\S]*?(?=\n\n|\n[A-Z]|$)/i,
    /This\s*Week:[\s\S]*?Next\s*Week:[\s\S]*?(?=\n\n|\n[A-Z]|$)/i
  ];
  
  let cleanedPurpose = currentPurpose;
  for (const pattern of dutyPatterns) {
    cleanedPurpose = cleanedPurpose.replace(pattern, '').trim();
  }
  
  // Remove extra blank lines
  cleanedPurpose = cleanedPurpose.replace(/\n{3,}/g, '\n\n').trim();
  
  // Combine existing content with new duty info
  if (cleanedPurpose) {
    return `${cleanedPurpose}\n\n${dutyText}`;
  } else {
    return dutyText;
  }
}

/**
 * Format the channel overview text with duty information
 */
function formatChannelOverviewText(dutyInfo, currentWeek, nextWeek) {
  let text = `🗓️ Janitor Duty Rota\n\n`;
  text += `This Week: ${dutyInfo.currentPerson} (${currentWeek})\n`;
  text += `Next Week: ${dutyInfo.nextPerson || 'TBD'} (${nextWeek})`;
  return text;
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

### Step 2: Set up Slack Webhook

1. **Go to your Slack workspace**
   - Navigate to [api.slack.com](https://api.slack.com)

2. **Create a new app**
   - Click "Create New App"
   - Choose "From scratch"
   - Give it a name like "Janitor Bot"
   - Select your workspace

3. **Enable Incoming Webhooks**
   - In your app settings, go to "Incoming Webhooks"
   - Toggle "Activate Incoming Webhooks" to On
   - Click "Add New Webhook to Workspace"
   - Choose the channel where you want notifications
   - Click "Allow"

4. **Copy the webhook URL**
   - Copy the webhook URL (starts with `https://hooks.slack.com/services/...`)

### Step 2b: Set up Slack Bot Token (Optional - for Channel Overview Updates)

**Yes, Slack supports editing the channel overview (description/purpose) via API!** This allows you to automatically update the channel's "About" section with the current duty information.

**How it works:** The script reads the current channel overview, removes any old duty information, preserves other content you may have there, and updates/adds the current duty information. This prevents duplication and ensures your channel overview stays clean and up-to-date.

To enable channel overview updates:

1. **Enable OAuth Scopes**
   - In your Slack app settings, go to "OAuth & Permissions"
   - Scroll down to "Scopes" → "Bot Token Scopes"
   - Add the following scopes:
     - `channels:write` (for public channels - to update channel purpose)
     - `groups:write` (for private channels - to update channel purpose)
     - `channels:read` (to read current channel info and preserve existing content)
     - `groups:read` (to read private channel info if needed)
   
2. **Install the app to your workspace**
   - Scroll up to "OAuth Tokens for Your Workspace"
   - Click "Install to Workspace"
   - Review and authorize the permissions
   - Copy the "Bot User OAuth Token" (starts with `xoxb-...`)

3. **Get your Channel ID**
   - In Slack, open your channel
   - Right-click on the channel name in the sidebar
   - Select "View channel details" or "Open channel details"
   - Scroll down to find the Channel ID (or copy it from the channel URL)
   - Channel ID format: `C1234567890` or `G1234567890` for private channels
   - Alternatively, you can get it from the channel URL: `https://yourworkspace.slack.com/archives/C1234567890`

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
   - Replace `YOUR_SLACK_WEBHOOK_URL_HERE` with your Slack webhook URL
   - (Optional) Replace `YOUR_SLACK_BOT_TOKEN_HERE` with your Bot User OAuth Token (only needed for channel overview updates)
   - (Optional) Replace `YOUR_SLACK_CHANNEL_ID_HERE` with your channel ID (only needed for channel overview updates)
   - Update `SHEET_NAME` if your sheet tab has a different name
   
   **Note:** If you don't provide the bot token and channel ID, the script will still send notifications via webhook, but won't update the channel overview.

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

5. **No notification sent**
   - Check the Apps Script execution log
   - Look for error messages in the console
   - Verify your sheet data format matches expectations

6. **Channel overview not updating**
   - Verify your Bot Token is correct and starts with `xoxb-`
   - Check that you've installed the app to your workspace after adding OAuth scopes
   - Verify the Channel ID is correct (should start with `C` for public channels or `G` for private channels)
   - Make sure you've added the required OAuth scopes: `channels:write` or `groups:write`
   - Check the Apps Script execution log for specific error messages
   - Note: Channel overview updates are optional - if they fail, webhook notifications will still work

### Testing Commands

- **Test notification**: Run `testNotification()` function
- **Check current duty**: Run `getCurrentWeekDuty()` function
- **View logs**: Go to Executions in the Apps Script editor

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
