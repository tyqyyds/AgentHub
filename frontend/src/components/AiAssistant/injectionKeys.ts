import type { InjectionKey, Ref } from 'vue'

export interface BallPosition { x: number; y: number }

export const ballPositionKey: InjectionKey<Ref<BallPosition>> = Symbol('ballPosition')
