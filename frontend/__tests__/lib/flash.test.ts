import { render, screen } from '@testing-library/react';
import { flashSuccessButton } from '../src/app/lib/flash';

describe('Utility Functions', () => {
  describe('flashSuccessButton', () => {
    it('should add and remove success class', () => {
      const button = document.createElement('button');
      button.id = 'test-button';
      document.body.appendChild(button);

      flashSuccessButton('test-button');

      // 等待class被添加
      setTimeout(() => {
        expect(button.classList.contains('flash-success')).toBe(true);
      }, 10);

      // 等待class被移除
      setTimeout(() => {
        expect(button.classList.contains('flash-success')).toBe(false);
      }, 310);

      document.body.removeChild(button);
    });
  });
});
