# e-flow Dashboard Styling Guide - Quick Reference

## Font Stack
```css
font-family: 'Helvetica Neue', 'Helvetica Neue Light', 
             -apple-system, BlinkMacSystemFont, 'Segoe UI', 
             'Roboto', 'Inter', sans-serif;
```

## Color Palette

| Element | Color | Usage |
|---------|-------|-------|
| Primary Blue | #0066cc | Buttons, metrics, accents |
| Dark Blue | #0052a3 | Button hover state |
| Text Primary | #1a1a1a | Headers, titles |
| Text Secondary | #333 | Body text |
| Text Tertiary | #666 | Captions, labels |
| Background | #f8f9fa | Info boxes |
| Light Background | #f0f7ff | Metric cards |
| Border | #e0e0e0 | Cards, containers |

## Typography Scale

| Element | Size | Weight | Letter-spacing |
|---------|------|--------|-----------------|
| h1 | 2.8rem | 600 | 0px |
| h2 | 2rem | 500 | 0.3px |
| h3 | 1.4rem | 500 | 0.3px |
| Body | 1rem | 300 | 0.3px |
| Metric Label | 0.9rem | 300 | 0.5px |
| Caption | 0.9rem | 300 | 0.2px |
| Small Info | 0.85rem | 300 | 0.2px |

## Component Styling

### Metric Cards
```css
background: linear-gradient(135deg, #f0f7ff 0%, #ffffff 100%);
border: 1px solid #e0e0e0;
border-radius: 12px;
padding: 20px;
min-height: 120px;
```

### Buttons
```css
background: linear-gradient(135deg, #0066cc 0%, #0052a3 100%);
color: white;
padding: 0.75rem 1.5rem;
border-radius: 8px;
box-shadow: 0 2px 8px rgba(0, 102, 204, 0.2);
```

### Info Boxes
```css
background: #f8f9fa;
border: 1px solid #e0e0e0;
border-radius: 8px;
padding: 1rem;
```

### Dividers
```css
border: none;
height: 1px;
background: linear-gradient(to right, #e0e0e0 0%, transparent);
margin: 2rem 0;
```

## Spacing Standards

| Use | Value |
|-----|-------|
| Section margin-top | 2rem |
| Section margin-bottom | 1rem |
| Container padding | 1rem or 1.5rem |
| Line height | 1.6 |
| Flexbox gap | medium |

## Interactive States

### Button Hover
```css
transform: translateY(-1px);
box-shadow: 0 4px 12px rgba(0, 102, 204, 0.4);
```

### Metric Card Hover
```css
box-shadow: 0 8px 16px rgba(0, 102, 204, 0.12);
transform: translateY(-2px);
```

## Responsive Breakpoints

- Desktop: Full width, 3-column layouts
- Tablet: Adjusted column widths
- Mobile: Stacked layouts, full-width cards

## Accessibility Notes

- Minimum font size: 0.85rem
- Color contrast: WCAG AA (4.5:1)
- Font-smoothing enabled
- Proper heading hierarchy maintained

## Implementation Files

- **Main CSS**: `app.py` (lines 47-220)
- **Styling Guide**: `STYLING_ENHANCEMENTS.md`
- **Visual Examples**: `VISUAL_IMPROVEMENTS.md`

## Key Principles

1. **Consistency**: All components use same font stack
2. **Hierarchy**: Clear size and weight differentiation
3. **Whitespace**: Generous spacing for luxury feel
4. **Professional**: Helvetica Neue conveys quality
5. **Accessible**: High contrast and readable fonts
6. **Performant**: System fonts, no external loads

## Common Pattern: Styled Metric Card

```html
<div style="background: linear-gradient(135deg, #f0f7ff 0%, #ffffff 100%); 
            padding: 20px; border-radius: 12px; border: 1px solid #e0e0e0;
            text-align: center; min-height: 120px; 
            display: flex; flex-direction: column; justify-content: center;">
    <p style="color: #666; font-size: 0.9rem; font-weight: 300; 
              margin: 0 0 0.5rem 0; letter-spacing: 0.5px;">
        LABEL
    </p>
    <p style="font-size: 2rem; font-weight: 400; margin: 0; color: #0066cc;">
        VALUE <span style="font-size: 1rem;">UNIT</span>
    </p>
</div>
```

## Testing Checklist

- [ ] Fonts render correctly (Helvetica Neue fallback)
- [ ] Colors display consistently across browsers
- [ ] Gradients render smoothly
- [ ] Buttons have hover effects
- [ ] Cards have proper spacing on mobile
- [ ] Text has sufficient contrast
- [ ] Letter-spacing doesn't exceed readability
- [ ] Animation performance is smooth
- [ ] Responsive layout works on all screens
- [ ] Print preview looks professional
