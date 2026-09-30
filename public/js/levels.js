export const LEVELS = {
  NONE: { label: 'No recent reports', css: 'none' },
  WATCH: { label: 'Watch', css: 'watch' },
  ALERT: { label: 'Alert', css: 'alert' },
  OUTBREAK: { label: 'Possible outbreak', css: 'outbreak' },
};

export const KINDS = {
  street_food: 'Street food',
  restaurant: 'Restaurant',
  tea_snack: 'Tea & snacks',
};

export const SYMPTOMS = [
  ['vomiting', 'Vomiting'],
  ['diarrhoea', 'Diarrhoea'],
  ['stomach_cramps', 'Stomach cramps'],
  ['nausea', 'Nausea'],
  ['fever', 'Fever'],
  ['blood_in_stool', 'Blood in stool'],
];

export const SYMPTOM_LABEL = Object.fromEntries(SYMPTOMS);
export const GI = new Set(['vomiting', 'diarrhoea', 'stomach_cramps', 'nausea', 'blood_in_stool']);

export const ACTION_TEXT = {
  sent: ['Report sent', ''],
  held: ['Held back by AI review', 'warn'],
  skipped_no_email: ['Email not configured', 'warn'],
  error: ['Email failed', 'warn'],
};
