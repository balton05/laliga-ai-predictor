import { Component, input, signal } from '@angular/core';

import { teamBadge } from '../core/team-assets';

@Component({
  selector: 'app-team-logo',
  standalone: true,
  template: `
    <span
      class="team-logo"
      [style.width.px]="size()"
      [style.height.px]="size()"
    >
      <img
        [src]="source()"
        [alt]="'Escudo de ' + teamName()"
        [attr.width]="size()"
        [attr.height]="size()"
        loading="lazy"
        (error)="useFallback()"
      >
    </span>
  `,
  styles: `
    :host {
      display: inline-flex;
      flex: 0 0 auto;
      line-height: 0;
    }

    .team-logo {
      display: grid;
      place-items: center;
      overflow: hidden;
    }

    img {
      display: block;
      width: 88%;
      height: 88%;
      object-fit: contain;
      filter: drop-shadow(0 7px 12px rgba(0, 0, 0, 0.28));
    }
  `,
})
export class TeamLogoComponent {
  readonly teamName = input.required<string>();
  readonly size = input(40);
  private readonly failed = signal(false);

  source(): string {
    return this.failed()
      ? 'assets/teams/default-team.svg'
      : teamBadge(this.teamName());
  }

  useFallback(): void {
    if (!this.failed()) this.failed.set(true);
  }
}
